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
import posixpath
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
    except RecursionError:
        # A document nested past what this validator can walk is refused,
        # never a crash of the whole run (engine-descriptor-v1.md §7.1).
        return False, "nested too deep to validate"


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


def present_files(root: pathlib.Path) -> set[str]:
    """Every file under `root`, as release-relative posix paths -- what a
    `.gltf`'s relative uri may name."""
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


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


class GltfFormatError(ValueError):
    """`E_CONTENT_FORMAT` (the content catalogue's ingest-v1.md §3 step 10,
    adopted so the two gates agree on every file): a GLB that is not whole,
    glTF JSON that does not parse or names a member twice, or an external
    reference."""


def _no_duplicate_members(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise GltfFormatError(f"the glTF JSON names {key!r} twice")
        out[key] = value
    return out


def _strict_json(data: bytes):
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=_no_duplicate_members)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise GltfFormatError(f"the glTF JSON does not parse: {e}") from None


def parse_glb_strict(raw: bytes) -> dict:
    """A GLB's JSON chunk, or GltfFormatError. The GLB must be whole: its
    header's total length equals the file's size and its first chunk is JSON
    and ends inside the file, so a chunk declared past EOF is never read as
    whatever bytes happen to be there. The JSON must parse with no member
    named twice -- one reader's `allowRedistribution: false` is another's
    `true`, and JSON that does not parse must never fall through to "plain",
    which an animation part does not judge."""
    if len(raw) < 20 or raw[0:4] != b"glTF":
        raise GltfFormatError("not a GLB")
    total = int.from_bytes(raw[8:12], "little")
    if total != len(raw):
        raise GltfFormatError(f"the GLB header says {total} bytes and the file has {len(raw)}")
    if raw[16:20] != b"JSON":
        raise GltfFormatError("the GLB's first chunk is not JSON")
    chunk_len = int.from_bytes(raw[12:16], "little")
    if 20 + chunk_len > len(raw):
        raise GltfFormatError("the GLB's JSON chunk runs past the end of the file")
    doc = _strict_json(raw[20:20 + chunk_len])
    if not isinstance(doc, dict):
        raise GltfFormatError("the glTF JSON is not an object")
    return doc


def gltf_uri_problem(doc: dict, is_glb: bool, path: str | None, present) -> str | None:
    """No external reference (ingest-v1.md §3 step 10): in a GLB every
    `images[].uri` and `buffers[].uri` is a `data:` URI; in a `.gltf` each is
    a `data:` URI or a plain relative path -- no scheme, no `..`, no leading
    `/`, no backslash -- naming a file the release holds (`present`, a set of
    release-relative paths; None skips that last test)."""
    for key in ("images", "buffers"):
        items = doc.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or "uri" not in item:
                continue
            u = item["uri"]
            if not isinstance(u, str):
                return f"a {key} uri that is not a string: {u!r}"
            if u.startswith("data:"):
                continue
            if is_glb:
                return f"a GLB names an external uri {u!r}"
            if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", u) or u.startswith("/") or "\\" in u \
                    or "/../" in f"/{u}/" or u in ("", "."):
                return f"a uri that is not a plain relative path: {u!r}"
            if present is not None and path is not None:
                target = posixpath.normpath(posixpath.join(posixpath.dirname(path), u))
                if target not in present:
                    return f"a uri naming a file the release does not hold: {u!r}"
    return None


def gltf_format_problem(raw: bytes, path: str | None = None, present=None) -> str | None:
    """Every GLB (by its magic) and every `.gltf`, in any part and of any
    class: the reason it is `E_CONTENT_FORMAT`, or None. Runs BEFORE
    classification."""
    is_glb = raw[:4] == b"glTF"
    if not is_glb and not (path is not None and path.lower().endswith(".gltf")):
        return None
    try:
        doc = parse_glb_strict(raw) if is_glb else _strict_json(raw)
    except GltfFormatError as e:
        return str(e)
    if not isinstance(doc, dict):
        return "the glTF JSON is not an object"
    return gltf_uri_problem(doc, is_glb, path, present)


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


def part_licence(entry: dict, raw, present=None) -> dict:
    """legal DRAFT-v3.md Part 6 G5: the licence_source decision for one
    covered [[integration.content]] entry, given the real bytes at its
    path (or None when nothing covers it). `licence_source` is `"vrm"`
    when readable, recognised VRM meta decided it (allowed or refused),
    `"declared"` when the manifest's own `licence` string is the whole
    licence, and `None` when neither exists -- `E_CONTENT_LICENCE_UNDECLARED`.
    `gate_status` is the VRM gate's own verdict
    ("ok"/"refused"/"conflict"/"unknown", or "format" for
    `E_CONTENT_FORMAT`, which every GLB and `.gltf` is held to before it is
    classified), or None when the gate does not apply: not a GLB or `.gltf`, an animation (`VRMC_vrm_animation` with no
    avatar extension), or a plain glTF in a part that is not a character.
    The gate runs on the bytes, never on the name, so a renamed avatar is
    judged as an avatar."""
    path = entry.get("path") if isinstance(entry, dict) else None
    gate_status = None
    vrm_licence = None
    refusal = None
    spath = path if isinstance(path, str) else None
    problem = gltf_format_problem(raw, spath, present) if raw is not None else None
    if problem is not None:
        gate_status = "format"
        refusal = {"field": "format", "detail": problem}
    doc = gltf_document(raw, spath) if raw is not None and problem is None else None
    if doc is not None:
        cls = gltf_class(doc)
        if cls == "avatar" or (cls == "plain" and entry.get("kind") == "character"):
            gate = vrm_gate(raw, spath, present)
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


def vrm_gate(raw: bytes, path: str | None = None, present=None) -> dict:
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
    problem = gltf_format_problem(raw, path, present)
    if problem is not None:
        return {"status": "format", "vrm_licence": None, "refusal": {"field": "format", "detail": problem}}
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


# ── mods (engine-descriptor-v1.md §7) ────────────────────────────────────
# The optional `mods` member: the player's own mod loaders. The schema's
# $defs/mods holds its shape (closed enums, §7.3 paths, the glob, the
# nesting); what a JSON Schema cannot express is below. Every rule reads
# `mods` and nothing else, and none of them can make a descriptor detect
# differently: the runner also holds that the descriptor without `mods` is
# the same valid descriptor whatever `mods` holds (§7.1).
#
# Nothing here recurses on the document: a `mods` nested 1,000 deep is
# walked with an explicit stack and refused, never a RecursionError (§7.1).

MODS_LOOKUPS = ("listed", "child", "stat")
MODS_COMBINATORS = ("any", "all", "none")

# The names mod loaders hijack-load by: merged plan §2.5 / plan A §4.5, kept
# by astra-game-launcher as src/plan.rs HIJACK_NAMES (Doorstop's names, the
# Ultimate ASI Loader's system-DLL names, ReShade's opengl32). A proxy says
# that SOME loader sits in a folder, never which, so it is never a loader
# anchor and never a chain entry (§7.4, §7.6).
HIJACK_NAMES = (
    "winhttp.dll", "version.dll", "dwmapi.dll", "dxgi.dll", "d3d11.dll", "dinput8.dll",
    "xinput1_1.dll", "xinput1_2.dll", "xinput1_3.dll", "xinput1_4.dll", "xinput9_1_0.dll",
    "xinputuap.dll", "winmm.dll", "dinput.dll", "dsound.dll", "d3d8.dll", "d3d9.dll",
    "d3d10.dll", "d3d12.dll", "ddraw.dll", "msacm32.dll", "msvfw32.dll", "wininet.dll",
    "xlive.dll", "opengl32.dll",
)

# §2.4's "must not itself be a program file", for §7.4's anchor and §7.6's
# entry: a name built from the game's own program, or a name that runs.
PROGRAM_PLACEHOLDERS = ("{program}", "{stem}", "{name}")
PROGRAM_EXTENSIONS = (".exe", ".com", ".bat", ".cmd", ".ps1", ".sh", ".x86", ".x86_64")

# §2.4's placeholder names; a descriptor's own `as` captures join them (§7.3).
PLACEHOLDERS = ("dir", "name", "stem", "program", "project", "project.leaf", "project.parent", "pak")

# §7.7: managers are launcher adapters (astra-game-launcher src/mods.rs
# ModManager: r2modman, Thunderstore, Gale; Mod Organizer 2 and Vortex
# later). Their names never appear in `mods`, as a member or as a value.
# The distinctive names match anywhere (r2modman's own folder is
# `r2modmanPlus-local`); the short ones only as a word (`nightingale` is not
# Gale). This is a list of names, so it is only the second line: the first
# is structural (§7.7) -- a descriptor reads below `{source}` and never
# chooses what `{source}` is.
_MANAGER_NAME = re.compile(
    r"r2modman|thunderstore|mod[ _-]?organi[sz]er|overwolf"
    r"|(?<![a-z0-9])(gale|mo2|vortex|tmm)(?![a-z0-9])",
    re.I,
)

MODS_BUDGET = {"lookups": 64, "probes": 8, "depth": 3}
# §7.1: tables and arrays, `mods` itself counted as 1. It follows from the
# schema: mods > loader[] > loader > require[] > three any/all/none levels
# (an array and an entry each) > a lookup.
MODS_MAX_NESTING = 11

_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*(?:\.[a-z]+)?)\}")
_DEVICE_STEMS = re.compile(r"^(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[0-9\u00b9\u00b2\u00b3]|LPT[0-9\u00b9\u00b2\u00b3])$")
_TEMPLATE = re.compile(r"^(?:N\{(?:1,[1-5]|2,[2-5]|3,[3-5]|4,[45]|5,5)\}|[A-Za-z.+_-]){1,32}$")
_VERSIONS = re.compile(r"^(?:=|<=?|>=?)[0-9A-Za-z.+_-]{1,32}(?:, (?:=|<=?|>=?)[0-9A-Za-z.+_-]{1,32})?$")
_CODE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")


def without_mods(doc: dict) -> dict:
    """The descriptor a reader that ignores `mods` evaluates (§7.1)."""
    return {k: v for k, v in doc.items() if k != "mods"}


def mods_schema(descriptor_schema: dict, definition: str = "mods") -> dict:
    """One of the $defs alone (default $defs/mods), resolving against the
    whole descriptor schema."""
    return {"$defs": descriptor_schema["$defs"], "$ref": f"#/$defs/{definition}"}


def reader_ignoring_mods_schema(descriptor_schema: dict) -> dict:
    """What launcher 0.5.0 checks: `mods`, when present, is a table, and
    nothing inside it is read."""
    s = json.loads(json.dumps(descriptor_schema))
    s["properties"]["mods"] = {"type": "object"}
    return s


# §4: ≤16 KiB serialized, `mods` included (§1: it is part of the canonical
# form). Sorted keys and no whitespace is JCS for these goldens, whose keys
# are ASCII and whose numbers are all integers.
DESCRIPTOR_BYTES = 16 * 1024


def canonical_size(doc) -> int | float:
    try:
        return len(json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    except RecursionError:
        return float("inf")


def reader_ignoring_mods_accepts(doc: dict, descriptor_schema: dict) -> bool:
    """Launcher 0.5.0's answer for the whole descriptor: `mods` is a table
    it does not read, and the canonical form still fits §4's bound."""
    return schema_ok(doc, reader_ignoring_mods_schema(descriptor_schema))[0] \
        and canonical_size(doc) <= DESCRIPTOR_BYTES


def nesting(value) -> int:
    """How deep tables and arrays nest in `value` (a container counts 1)."""
    deepest, stack = 0, [(value, 1)]
    while stack:
        v, d = stack.pop()
        if isinstance(v, dict):
            deepest = max(deepest, d)
            stack.extend((x, d + 1) for x in v.values())
        elif isinstance(v, list):
            deepest = max(deepest, d)
            stack.extend((x, d + 1) for x in v)
    return deepest


def _strings(value):
    stack = [value]
    while stack:
        v = stack.pop()
        if isinstance(v, dict):
            for k, x in v.items():
                yield k
                stack.append(x)
        elif isinstance(v, list):
            stack.extend(v)
        elif isinstance(v, str):
            yield v


def mods_loaders(doc: dict) -> list[dict]:
    mods = doc.get("mods")
    if not isinstance(mods, dict) or not isinstance(mods.get("loader"), list):
        return []
    return [l for l in mods["loader"] if isinstance(l, dict)]


def _require_walk(entries, limit: int = MODS_BUDGET["depth"] + 1):
    """(entry, combinator depth) for every lookup or probe in a `require`,
    with an explicit stack. A combinator deeper than `limit` is yielded
    itself, at that depth, and never descended into."""
    stack = [(entries, 0)]
    while stack:
        es, d = stack.pop()
        if not isinstance(es, list):
            continue
        for e in es:
            if not isinstance(e, dict):
                continue
            nested = next((k for k in MODS_COMBINATORS if k in e), None)
            if nested is None:
                yield e, d
            elif d + 1 > limit:
                yield e, d + 1
            else:
                stack.append((e[nested], d + 1))


def component_problem(c: str, placeholders: bool = True) -> str | None:
    """§7.3's component rules (astra-game-launcher src/paths.rs
    check_component, plus C1 controls): None, `path-escapes` or
    `path-invalid`."""
    if c == "..":
        return "path-escapes"
    if c in ("", ".") or len(c) > 255:
        return "path-invalid"
    if any(ord(ch) < 0x20 or 0x7F <= ord(ch) <= 0x9F or ch in '\\:*?<>"|/' for ch in c):
        return "path-invalid"
    bare = _PLACEHOLDER.sub("", c) if placeholders else c
    if "{" in bare or "}" in bare or (placeholders and "{source}" in c):
        return "path-invalid"
    if c.endswith(".") or c.endswith(" "):
        return "path-invalid"
    if _DEVICE_STEMS.match(c.split(".")[0].rstrip(" ").upper()):
        return "path-invalid"
    return None


def mods_path_reason(p) -> str | None:
    """None for a §7.3 path, else its §7.9 reason."""
    if not isinstance(p, str) or len(p) > 512:
        return "shape"
    if p == "{source}":
        return None
    if not p.startswith("{source}/"):
        return "path-outside-jail"
    found = [component_problem(c) for c in p.split("/")[1:]]
    if "path-escapes" in found:
        return "path-escapes"
    return "path-invalid" if any(found) else None


def substitute(path: str, values: dict) -> list[str] | None:
    """§7.3 at evaluation: every placeholder replaced by its game-relative
    value, the path split on `/` again, every component checked again.
    None = that loader yields nothing (an unbound placeholder, a value that
    is empty, holds `..`, a separator of its own or a placeholder)."""
    if mods_path_reason(path) is not None:
        return None
    missing = []

    def value(m):
        if m.group(1) not in values:
            missing.append(m.group(1))
            return ""
        return values[m.group(1)]

    rest = _PLACEHOLDER.sub(value, path[len("{source}"):])
    if missing:
        return None
    comps = rest.split("/")[1:] if rest else []
    if any(component_problem(c, placeholders=False) for c in comps):
        return None
    return comps


def file_name_reason(n) -> str | None:
    """§7.5's `marker`: one §7.3 component, no placeholder."""
    if not isinstance(n, str):
        return "shape"
    return "path-invalid" if component_problem(n, placeholders=False) else None


def glob_reason(g) -> str | None:
    """§7.5: one file name, one or two `*`, no other wildcard or separator."""
    ok = (isinstance(g, str) and 1 <= len(g) <= 64 and 1 <= g.count("*") <= 2 and "**" not in g
          and not any(ord(ch) < 0x20 or 0x7F <= ord(ch) <= 0x9F or ch in '/\\:?[]{}<>"|' for ch in g))
    return None if ok else "glob-over-budget"


def _mods_paths(loader: dict):
    """(member, path) for every §7.3 path a loader holds."""
    if "root" in loader:
        yield "root", loader["root"]
    for entry, _d in _require_walk(loader.get("require")):
        for k in MODS_LOOKUPS + ("tail",):
            if k in entry:
                yield f"require.{k}", entry[k]
    if isinstance(loader.get("version"), dict) and "pe" in loader["version"]:
        yield "version.pe", loader["version"]["pe"]
    for f in loader.get("enabled", []) if isinstance(loader.get("enabled"), list) else []:
        if isinstance(f, dict) and "list" in f:
            yield "enabled.list", f["list"]
    for s in loader.get("coexist", []) if isinstance(loader.get("coexist"), list) else []:
        if isinstance(s, dict) and "entry" in s:
            yield "coexist.entry", s["entry"]


def _anchor_name(path: str) -> str:
    """The literal part of a path's last component (its placeholders cut)."""
    return _PLACEHOLDER.sub("", path.rsplit("/", 1)[-1])


def _proxy_or_runtime(path: str) -> bool:
    name = _anchor_name(path)
    return name.lower() in HIJACK_NAMES or any(p.match(name) for p in _UBIQUITOUS)


def _program_shaped(path: str) -> bool:
    last = path.rsplit("/", 1)[-1]
    return any(p in last for p in PROGRAM_PLACEHOLDERS) or last.lower().endswith(PROGRAM_EXTENSIONS)


def _top_lookups(loader: dict, kind: str):
    """The top-level `listed`/`child`/`stat` paths of `kind` in a loader's
    `require` (never one inside any/all/none)."""
    req = loader.get("require")
    for entry in req if isinstance(req, list) else []:
        if isinstance(entry, dict) and entry.get("kind") == kind:
            key = next((k for k in MODS_LOOKUPS if k in entry), None)
            if key is not None and isinstance(entry[key], str):
                yield entry[key]


def _passive(loader: dict) -> bool:
    """§7.4, exactly: no `chain` strategy in `coexist`, and no `tell` in any
    strategy. A passive loader never makes Astra load or tell anything."""
    co = loader.get("coexist")
    return isinstance(co, list) and all(
        isinstance(s, dict) and s.get("strategy") != "chain" and "tell" not in s for s in co)


def _file_anchors(loader: dict) -> list[str]:
    """§7.4: top-level `file` lookups whose last component holds a literal
    name that is not a proxy, not a ubiquitous runtime and not the game's
    own program."""
    return [p for p in _top_lookups(loader, "file")
            if _anchor_name(p) and not _proxy_or_runtime(p) and not _program_shaped(p)]


def _root_anchored(loader: dict) -> bool:
    """§7.4: anchored on its root -- no file anchor, and a top-level `dir`
    lookup of exactly its own `root`."""
    return not _file_anchors(loader) and any(
        p == loader.get("root") and _anchor_name(p) for p in _top_lookups(loader, "dir"))


def rule_mods_loader_anchor_invalid(doc: dict) -> bool:
    """True = OK. §7.4: every loader is anchored -- by a file, or on its own
    root. Whether a root-anchored loader may be so is the next rule's."""
    return all(_file_anchors(l) or _root_anchored(l) for l in mods_loaders(doc))


def rule_mods_root_anchor_not_passive(doc: dict) -> bool:
    """True = OK. §7.4: a root-anchored loader is passive. One that also
    declares `chain` or a `tell` is refused, so that a later member can never
    quietly make a root-anchored loader active: an active loader needs a
    file anchor."""
    return all(_passive(l) for l in mods_loaders(doc) if _root_anchored(l))


def rule_mods_chain_entry_invalid(doc: dict) -> bool:
    """True = OK. §7.6: a `chain` entry is one of the loader's own top-level
    `file` lookups -- a file its recognition already found -- and is never a
    proxy, a ubiquitous runtime or the game's own program."""
    for loader in mods_loaders(doc):
        own = set(_top_lookups(loader, "file"))
        for s in loader.get("coexist", []) if isinstance(loader.get("coexist"), list) else []:
            if not isinstance(s, dict) or s.get("strategy") != "chain" or not isinstance(s.get("entry"), str):
                continue
            e = s["entry"]
            if e not in own or _proxy_or_runtime(e) or _program_shaped(e):
                return False
    return True


def descriptor_captures(doc: dict) -> set[str]:
    """Every `as` capture this descriptor's detection rules bind."""
    out, stack = set(), [doc.get("rule")]
    while stack:
        v = stack.pop()
        if isinstance(v, dict):
            if isinstance(v.get("as"), str):
                out.add(v["as"])
            stack.extend(v.values())
        elif isinstance(v, list):
            stack.extend(v)
    return out


def rule_mods_placeholder_unknown(doc: dict) -> bool:
    """True = OK. §7.3: a placeholder in a `mods` path is a §2.4 name or one
    of this descriptor's own captures."""
    known = set(PLACEHOLDERS) | descriptor_captures(doc)
    for loader in mods_loaders(doc):
        for _member, p in _mods_paths(loader):
            if isinstance(p, str) and set(_PLACEHOLDER.findall(p)) - known - {"source"}:
                return False
    return True


def rule_mods_code_undeclared(doc: dict) -> bool:
    """True = OK. §7.4: a loader's `codes` are this descriptor's own."""
    own = set(doc.get("engine", {}).get("codes", {}).keys()) if isinstance(doc.get("engine"), dict) else set()
    return all(set(l.get("codes", [])) <= own for l in mods_loaders(doc) if isinstance(l.get("codes", []), list))


def rule_mods_loader_id_duplicate(doc: dict) -> bool:
    """True = OK. §7.2: loader ids are unique within the descriptor."""
    ids = [l.get("id") for l in mods_loaders(doc)]
    return len(ids) == len(set(map(str, ids)))


def mods_cost(doc: dict) -> dict:
    """§7.8's per-member counts: lookups (`listed`/`child`/`stat`), content
    probes (`tail`, a `version`, an `enable-list` list and its `marker`) and
    the deepest `any`/`all`/`none` nesting, across every loader."""
    lookups = probes = depth = 0
    for loader in mods_loaders(doc):
        for entry, d in _require_walk(loader.get("require")):
            depth = max(depth, d)
            if any(k in entry for k in MODS_LOOKUPS):
                lookups += 1
            elif "tail" in entry:
                probes += 1
        if isinstance(loader.get("version"), dict):
            probes += 1
        for fmt in loader.get("enabled", []) if isinstance(loader.get("enabled"), list) else []:
            if isinstance(fmt, dict) and fmt.get("format") == "enable-list":
                probes += 1 + ("marker" in fmt)
    return {"lookups": lookups, "probes": probes, "depth": depth}


def rule_mods_over_budget(doc: dict) -> bool:
    """True = OK. §7.8: ≤64 lookups, ≤8 probes, any/all/none ≤3 deep, and
    §7.1's nesting bound, per member."""
    cost = mods_cost(doc)
    return all(cost[k] <= MODS_BUDGET[k] for k in MODS_BUDGET) and nesting(doc.get("mods")) <= MODS_MAX_NESTING


def rule_mods_manager_as_data(doc: dict) -> bool:
    """True = OK. §7.7: no mod manager is named anywhere in `mods`, as a
    member or as a value -- a manager is a launcher adapter, never data."""
    return not any(_MANAGER_NAME.search(s) for s in _strings(doc.get("mods")))


SEMANTIC_MODS_RULES = {
    "mods-loader-anchor-invalid": rule_mods_loader_anchor_invalid,
    "mods-root-anchor-not-passive": rule_mods_root_anchor_not_passive,
    "mods-chain-entry-invalid": rule_mods_chain_entry_invalid,
    "mods-placeholder-unknown": rule_mods_placeholder_unknown,
    "mods-code-undeclared": rule_mods_code_undeclared,
    "mods-loader-id-duplicate": rule_mods_loader_id_duplicate,
    "mods-over-budget": rule_mods_over_budget,
    "mods-manager-as-data": rule_mods_manager_as_data,
}

# §7.9's reason for each semantic rule.
SEMANTIC_MODS_REASONS = {
    "mods-loader-anchor-invalid": "loader-anchor-invalid",
    "mods-root-anchor-not-passive": "root-anchor-not-passive",
    "mods-chain-entry-invalid": "chain-entry-invalid",
    "mods-placeholder-unknown": "placeholder-unknown",
    "mods-code-undeclared": "code-undeclared",
    "mods-loader-id-duplicate": "loader-id-duplicate",
    "mods-over-budget": "over-budget",
    "mods-manager-as-data": "manager-as-data",
}


def mods_semantic_problems(doc: dict) -> list[str]:
    return [name for name, rule in SEMANTIC_MODS_RULES.items() if not rule(doc)]


_LOADER_KEYS = {"id", "name", "codes", "source", "require", "version", "root", "enabled", "coexist"}
_LOADER_REQUIRED = {"id", "name", "source", "require", "root", "enabled", "coexist"}
_ENABLED_KEYS = {"dir-per-mod": ({"format"}, {"format"}),
                 "enable-list": ({"format", "list", "line", "marker"}, {"format", "list", "line"}),
                 "file-glob": ({"format", "glob"}, {"format", "glob"})}
_COEXIST_KEYS = {"chain": ({"strategy", "entry", "tell"}, {"strategy", "entry"}),
                 "side-by-side": ({"strategy", "tell"}, {"strategy"}),
                 "via-manager": ({"strategy"}, {"strategy"})}


def _list(v, lo, hi) -> bool:
    return isinstance(v, list) and lo <= len(v) <= hi


def mods_reasons(doc: dict) -> set[str]:
    """Every §7.9 reason a descriptor's `mods` is refused for, read from the
    grammar itself and not from the schema's error text, so the reason a
    golden is NAMED for can be asserted (vectors.json `reasons`). Empty for a
    valid `mods`, or for none at all."""
    if "mods" not in doc:
        return set()
    m = doc["mods"]
    if not isinstance(m, dict):
        return {"descriptor-invalid"}
    r = set()
    if nesting(m) > MODS_MAX_NESTING:
        r.add("over-budget")
    if set(m) - {"loader"}:
        r.add("unknown")
    loaders = m.get("loader")
    if not _list(loaders, 1, 4):
        r.add("shape")
    for l in loaders if isinstance(loaders, list) else []:
        if not isinstance(l, dict):
            r.add("shape")
            continue
        if set(l) - _LOADER_KEYS:
            r.add("unknown")
        if _LOADER_REQUIRED - set(l):
            r.add("shape")
        if "id" in l and not (isinstance(l["id"], str) and _CODE.match(l["id"])):
            r.add("shape")
        if "name" in l and not (isinstance(l["name"], str) and 1 <= len(l["name"]) <= 48):
            r.add("shape")
        if "codes" in l and not (_list(l["codes"], 1, 4) and all(isinstance(c, str) and _CODE.match(c) for c in l["codes"])):
            r.add("shape")
        if "source" in l:
            if not _list(l["source"], 1, 3):
                r.add("shape")
            elif any(s not in ("game", "manager", "picked") for s in l["source"]):
                r.add("unknown")
        if "require" in l and not _list(l["require"], 1, 8):
            r.add("shape")
        for entry, d in _require_walk(l.get("require")):
            if d > MODS_BUDGET["depth"]:
                r.add("over-budget")
                continue
            key = next((k for k in MODS_LOOKUPS + ("tail",) if k in entry), None)
            if key is None:
                r.add("unknown")
                continue
            allowed = {key, "kind"} if key != "tail" else {"tail", "bytes", "equals", "min_len"}
            if set(entry) - allowed:
                r.add("unknown")
            if key != "tail":
                if "kind" not in entry:
                    r.add("shape")
                elif entry["kind"] not in ("file", "dir"):
                    r.add("unknown")
        v = l.get("version")
        if v is not None:
            if not isinstance(v, dict):
                r.add("shape")
            else:
                if set(v) - {"pe", "key", "template", "versions"}:
                    r.add("unknown")
                if {"pe", "key", "template"} - set(v):
                    r.add("shape")
                if "key" in v:
                    if not _list(v["key"], 1, 2):
                        r.add("shape")
                    elif any(k not in ("ProductVersion", "FileVersion") for k in v["key"]):
                        r.add("unknown")
                if "template" in v and not (isinstance(v["template"], str) and _TEMPLATE.match(v["template"])):
                    r.add("version-invalid")
                if "versions" in v and not (isinstance(v["versions"], str) and _VERSIONS.match(v["versions"])):
                    r.add("version-invalid")
        en = l.get("enabled")
        if "enabled" in l and not _list(en, 1, 3):
            r.add("shape")
        for f in en if isinstance(en, list) else []:
            if not isinstance(f, dict) or f.get("format") not in _ENABLED_KEYS:
                r.add("unknown" if isinstance(f, dict) else "shape")
                continue
            allowed, required = _ENABLED_KEYS[f["format"]]
            if set(f) - allowed:
                r.add("unknown")
            if required - set(f):
                r.add("shape")
            if "line" in f and f["line"] != "name-colon-flag":
                r.add("unknown")
            if "marker" in f:
                r.add(file_name_reason(f["marker"]))
            if "glob" in f:
                r.add(glob_reason(f["glob"]))
        co = l.get("coexist")
        if "coexist" in l and not _list(co, 0, 3):
            r.add("shape")
        for s in co if isinstance(co, list) else []:
            if not isinstance(s, dict) or s.get("strategy") not in _COEXIST_KEYS:
                r.add("unknown" if isinstance(s, dict) else "shape")
                continue
            allowed, required = _COEXIST_KEYS[s["strategy"]]
            if set(s) - allowed:
                r.add("unknown")
            if required - set(s):
                r.add("shape")
            if "tell" in s and s["tell"] not in ("ue4ss-mods-paths",):
                r.add("unknown")
        for _member, p in _mods_paths(l):
            r.add(mods_path_reason(p))
    for name, rule in SEMANTIC_MODS_RULES.items():
        if not rule(doc):
            r.add(SEMANTIC_MODS_REASONS[name])
    r.discard(None)
    return r


def _template_regex(template: str, runs: int | None = None) -> tuple[str, int]:
    """§2.5's version template as a regex with one group per digit run, cut
    after the `runs`-th run when given. Returns (regex, runs it holds)."""
    out, n, i = [], 0, 0
    while i < len(template):
        m = re.match(r"N\{(\d),(\d)\}", template[i:])
        if m:
            out.append(f"([0-9]{{{m.group(1)},{m.group(2)}}})")
            n += 1
            i += m.end()
            if runs is not None and n == runs:
                break
        else:
            out.append(re.escape(template[i]))
            i += 1
    return "".join(out), n


def read_version(template: str, value: str) -> list[int] | None:
    """§7.4: the digit runs of the template's match at the start of `value`,
    whose next character is not a digit; None when it does not match, and
    None for a template §7.4 refuses (`N{5,1}`), never an exception."""
    if not _TEMPLATE.match(template):
        return None
    rx, _ = _template_regex(template)
    m = re.match(rx + r"(?![0-9])", value)
    return [int(g) for g in m.groups()] if m else None


def read_operand(template: str, operand: str) -> list[int] | None:
    """§7.4: an operand is the template's leading part, cut after a digit
    run; its runs, or None when it does not read in the template's shape."""
    if not _TEMPLATE.match(template):
        return None
    _, total = _template_regex(template)
    for k in range(1, total + 1):
        rx, _ = _template_regex(template, k)
        m = re.fullmatch(rx, operand)
        if m:
            return [int(g) for g in m.groups()]
    return None


def version_comparators(versions: str) -> list[tuple[str, str]]:
    """`>=5.4, <5.5` -> [(">=", "5.4"), ("<", "5.5")]."""
    return [re.match(r"(<=|>=|=|<|>)(.*)$", c).groups() for c in versions.split(", ")]


def version_holds(template: str, versions: str, value: str) -> bool:
    """§7.4: whether `value`'s version satisfies every comparator. Unknown
    (no match, a template or `versions` that does not read, or an operand
    out of the template's shape) never holds."""
    if not _VERSIONS.match(versions):
        return False
    have = read_version(template, value)
    if have is None:
        return False
    for op, operand in version_comparators(versions):
        want = read_operand(template, operand)
        if want is None:
            return False
        got = have[:len(want)]
        if not {"=": got == want, "<": got < want, "<=": got <= want,
                ">": got > want, ">=": got >= want}[op]:
            return False
    return True


def mods_compat(doc: dict, twin: dict, descriptor_schema: dict) -> dict:
    """§7.1 for one golden carrying `mods`: the full schema's verdict, the
    `mods` table's own (schema and semantic), the 0.5.0 reader's view, and
    whether the descriptor without `mods` is `twin`, a valid descriptor."""
    return {
        "full": schema_ok(doc, descriptor_schema)[0],
        "mods": schema_ok(doc.get("mods"), mods_schema(descriptor_schema))[0] and not mods_semantic_problems(doc),
        "reader": reader_ignoring_mods_accepts(doc, descriptor_schema),
        "twin": "mods" in doc and without_mods(doc) == twin and schema_ok(twin, descriptor_schema)[0],
    }


def _dig(doc: dict, dotted: str):
    for part in dotted.split("."):
        doc = doc[part]
    return doc


def judge_mods_paths(cases: dict, descriptor_schema: dict) -> list[tuple[str, bool, str]]:
    """testdata/games/descriptors/mods/paths.json: each path's schema verdict
    and §7.9 reason, and each substitution's re-checked components (§7.3)."""
    out = []
    path_schema = mods_schema(descriptor_schema, "modsPath")
    for c in cases["paths"]:
        sok = schema_ok(c["path"], path_schema)[0]
        got = mods_path_reason(c["path"])
        out.append((f"descriptor/mods/paths/{c['path']!r}", sok == (c["reason"] is None) and got == c["reason"],
                    f"schema_ok={sok} reason={got} want={c['reason']}"))
    for c in cases["substitution"]:
        got = substitute(c["path"], c["values"])
        out.append((f"descriptor/mods/substitution/{c['path']} {c['values']}", got == c["components"],
                    f"got={got} want={c['components']}"))
    return out


def judge_mods_hostile(v: dict, doc: dict, descriptor_schema: dict) -> list[tuple[str, bool, str]]:
    """One hostile `mods` golden: refused as recorded, refused INSIDE `mods`
    (the detection half stands on its own, §7.9), for exactly the recorded
    §7.9 reasons, and by the one semantic rule it is named for."""
    out = []
    sok, detail = schema_ok(doc, descriptor_schema)
    mods_sok, _ = schema_ok(doc.get("mods"), mods_schema(descriptor_schema))
    out.append((f"descriptor/mods/hostile/{v['name']} (schema)",
                sok == (v["schema_verdict"] == "accept") and mods_sok == sok, detail))
    det_ok, det_detail = schema_ok(without_mods(doc), descriptor_schema)
    reader_ok = reader_ignoring_mods_accepts(doc, descriptor_schema)
    out.append((f"descriptor/mods/hostile/{v['name']} (client)",
                det_ok and "mods" in doc and reader_ok == (v["reader_ignoring_mods"] == "accept"), det_detail))
    reasons = sorted(mods_reasons(doc))
    out.append((f"descriptor/mods/hostile/{v['name']} (reasons)", reasons == sorted(v["reasons"]),
                f"got {reasons}, want {sorted(v['reasons'])}"))
    problems = mods_semantic_problems(doc)
    want = [v["rule"]] if v["check"] == "semantic" else []
    out.append((f"descriptor/mods/hostile/{v['name']} (semantic)", problems == want, f"{problems}"))
    return out


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

    # -- mods (engine-descriptor-v1.md §7) ----------------------------------
    mv = vectors["descriptors"]["mods"]
    for name, ok, detail in judge_mods_paths(load_doc(mv["paths"]), descriptor_schema):
        report(name, ok, detail)
    for v in mv["builtin"]:
        frag = load_doc(v["file"])
        eng = load_doc(v["engine"])
        whole = dict(eng, mods=frag.get("mods"))
        sok, detail = schema_ok(whole, descriptor_schema)
        reasons = mods_reasons(whole)
        loaders = {l["id"]: l for l in mods_loaders(whole)}
        operands_read = all(
            read_operand(l["version"]["template"], operand) is not None
            for l in loaders.values() if "versions" in l.get("version", {})
            for _op, operand in version_comparators(l["version"]["versions"])
        )
        chain_incapable = all(
            i in loaders and not any(s.get("strategy") == "chain" for s in loaders[i]["coexist"])
            for i in v.get("chain_incapable", [])
        )
        ok = (
            set(frag) == {"schema", "mods"} and frag["schema"] == eng["schema"]
            and sok and not reasons and list(loaders) == v["loaders"]
            and without_mods(whole) == eng and operands_read and chain_incapable
        )
        report(f"descriptor/mods/builtin/{v['name']}", ok == (v["verdict"] == "accept"),
               f"schema={detail or 'ok'} reasons={sorted(reasons)} loaders={list(loaders)}")

    for v in mv["compat"]:
        doc = load_doc(v["file"])
        twin = _dig(load_doc(v["twin"]), v["twin_at"])
        c = mods_compat(doc, twin, descriptor_schema)
        reasons = sorted(mods_reasons(doc))
        ok = (
            c["full"] == (v["verdict"] == "accept")
            and c["mods"] == (v["mods_verdict"] == "accept")
            and c["reader"] == (v["reader_ignoring_mods"] == "accept")
            and c["twin"] and reasons == sorted(v["reasons"])
        )
        report(f"descriptor/mods/compat/{v['name']}", ok, json.dumps(dict(c, reasons=reasons)))

    for v in mv["hostile"]:
        for name, ok, detail in judge_mods_hostile(v, load_doc(v["file"]), descriptor_schema):
            report(name, ok, detail)

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
                pl = part_licence(entry, raw, present_files(DATA / v["dir"]))
                if pl["gate_status"] in ("refused", "conflict", "format"):
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
            elif v["verdict"] == "format":
                ok = gate["status"] == "format" and v["detail"] in gate["refusal"]["detail"]
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
