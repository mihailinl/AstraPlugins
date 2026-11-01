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

import hashlib
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
#
# Where the content catalogue already decides a question -- the text-glTF
# sniff, the `%?#\` URI rule, the 16 MiB / depth-128 / 32 MiB caps, a whole
# `.astrachar`/`.astrapack` -- this section CALLS spec/content's own
# reference checker (tools/check-content-goldens.py, with
# tools/contentlite.py) instead of restating it, so the two gates cannot
# drift apart one file at a time. Only what a game integration does
# differently is written here (manifest.md §2.7.1, §2.7.3).

def _load_content_checker():
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_content_goldens", ROOT / "tools" / "check-content-goldens.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CG = _load_content_checker()  # spec/content/ingest-v1.md §3-§4, the content contract's own code
MANIFEST_NAME = "astra-gi.toml"
_GEN = None


def gen_module():
    """testdata/games/content/vrm/gen.py, for the release goldens too large to
    commit (`synth`, built in memory and pinned by sha256 in vectors.json)."""
    global _GEN
    if _GEN is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("games_content_gen", DATA / "content" / "vrm" / "gen.py")
        _GEN = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_GEN)
    return _GEN


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


def is_manifest(path: str) -> bool:
    """The manifest is `astra-gi.toml` at the release root. A file of that
    name in any folder is an ordinary file, judged by its bytes: matching the
    basename let a prohibited VRM saved as `models/astra-gi.toml` publish."""
    return path == MANIFEST_NAME


def release_files(root: pathlib.Path) -> dict[str, bytes]:
    """Every file of a release, the manifest included, keyed by its
    release-relative posix path: what the content check reads BY BYTES
    (manifest.md §2.7.1), not only the files a name makes content-typed."""
    if not root.is_dir():
        return {}
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def is_content_typed(path: str, raw: bytes) -> bool:
    """manifest.md §2.7.1's table: extension AND magic, never one alone. The
    manifest file itself -- `astra-gi.toml` at the release ROOT, nowhere
    else -- is never a content file."""
    if is_manifest(path):
        return False
    sniff = CONTENT_EXT_MAGIC.get(pathlib.PurePosixPath(path).suffix.lower())
    return sniff is not None and sniff(raw[:32])


def content_files_of(files: dict[str, bytes]) -> dict[str, bytes]:
    return {p: b for p, b in sorted(files.items()) if is_content_typed(p, b)}


def find_content_files(root: pathlib.Path) -> dict[str, bytes]:
    """Every file under `root` whose extension AND magic bytes both say it is
    content-typed (manifest.md §2.7.1), keyed by its path relative to `root`
    (posix-style, matching a [[integration.content]] `path`). The manifest
    file itself is never a content file."""
    return content_files_of(release_files(root))


# ── content by bytes, for EVERY file (manifest.md §2.7.1) ────────────────
# A name never decides whether a file is content. A GLB under any name but
# .vrm/.glb/.vrma, or a text glTF under any name but .gltf, is refused
# E_CONTENT_FORMAT -- otherwise a prohibited avatar ships as `data/a.bin`
# and the gate never opens it, while three.js (which sniffs the magic) loads
# it. The text sniff is the content catalogue's own `is_gltf_json`. Two
# deliberate differences, because a game integration ships arbitrary files
# and the content catalogue does not:
#   * a UTF-16/32 byte-order mark is not refused (localisation files carry
#     one); such a text is instead sniffed as the text it DECODES to, since
#     a reader that decodes by the BOM (fetch().text() does) sees that text;
#   * over 16 MiB the key-by-key sniff is not run (it is a Python loop over
#     every character); a JSON-looking file that large is refused when its
#     bytes name an `asset` key at all -- spelt plainly or with \u escapes,
#     which JSON decodes to the same key -- and accepted otherwise. Nothing
#     that large is a glTF the gate would accept anyway (16 MiB cap, below).

_BOM_CODECS = dict(zip(CG.UNICODE_BOMS, ("utf-32-be", "utf-32-le", "utf-16-le", "utf-16-be")))
_ASSET_KEY = re.compile(rb'"(?:a|\\u0061)(?:s|\\u0073)(?:s|\\u0073)(?:e|\\u0065)(?:t|\\u0074)"')


def sniff_text(raw: bytes) -> bytes:
    """The UTF-8 text a BOM-honouring reader sees: a UTF-16/32 text decoded
    by its byte-order mark, anything else as it is."""
    for bom, codec in _BOM_CODECS.items():
        if raw.startswith(bom):
            return raw[len(bom):].decode(codec, "replace").encode("utf-8")
    return raw


def is_text_gltf(raw: bytes) -> bool:
    """The content catalogue's text-glTF sniff (`is_gltf_json`, S5/N1), over
    the text a BOM-honouring reader sees, and the cheap test above 16 MiB."""
    text = sniff_text(raw)
    if len(raw) > CG.MAX_GLTF_JSON:
        body = text[len(CG.UTF8_BOM):] if text.startswith(CG.UTF8_BOM) else text
        return body.lstrip(b" \t\r\n")[:1] == b"{" and _ASSET_KEY.search(body) is not None
    return CG.is_gltf_json(text)


def name_problem(path: str, raw: bytes) -> str | None:
    """Why a file's name and its bytes disagree (E_CONTENT_FORMAT), or None.
    Runs on every file of the release, declared or not."""
    if is_manifest(path):
        return None
    if raw[:4] == CG.GLB_MAGIC:
        # the content catalogue's own name rule, one way: a GLB is named as one
        return None if CG.name_matches_magic(path, raw) else "a GLB (it begins with glTF) named something not .vrm, .glb or .vrma"
    if not path.lower().endswith(".gltf") and is_text_gltf(raw):
        if len(raw) > CG.MAX_GLTF_JSON:
            return f"a JSON text over 16 MiB ({len(raw)} bytes) that names an asset key, named something not .gltf"
        return "a text glTF (a JSON object with a top-level asset member) named something not .gltf"
    if _is_zip(raw[:4]) and not path.lower().endswith(BUNDLE_EXTS) and is_bundle_bytes(raw):
        return "a content bundle (a zip whose last entry is astrachar.json) named something not .astrachar or .astrapack"
    return None


# ── an embedded .astrachar / .astrapack (manifest.md §2.7.3) ──────────────
# A bundle inside a game integration's release is judged by the content
# contract's OWN code, `ingest_bundle`: walk_zip and ingest-v1.md §3 steps
# 1-8, 10, 11 and step 12's every-file-in-a-part rule. Step 9 (the server's
# blocklist) has no list here and is skipped; step 12's parts-mismatch half
# has nothing to compare, since a game integration declares no part digests.
# The part's declared `licence` stands for every part of the bundle (content's
# `declared_licence`); without one, each bundle part needs its own allowed
# VRM meta. Content's Unknown is held there for a moderator and published
# flagged here (F_CONTENT_VRM_META_UNKNOWN), as for a bare VRM.

BUNDLE_EXTS = (".astrachar", ".astrapack")


def is_bundle_bytes(raw: bytes) -> bool:
    """ingest-v1.md §3: a bundle is a zip whose LAST entry is
    `astrachar.json` -- read with content's own walk_zip, so only an archive
    Astra's importer would open as a bundle counts as one."""
    if not _is_zip(raw[:4]) or b"astrachar.json" not in raw:
        return False
    try:
        order = json.loads(CG.walk_zip(raw)["\0order"])
    except Exception:  # noqa: BLE001 -- refused or unreadable: no importer opens it as a bundle
        return False
    return bool(order) and order[-1] == "astrachar.json"


def _bundle_layout(raw: bytes):
    """(part roots, body path, body bytes) by content's own reading, or
    ([], None, None) when it cannot read that far -- `ingest_bundle` then
    refuses the bundle with the step that failed."""
    try:
        files = CG.walk_zip(raw)
        files.pop("\0order", None)
        man = CG.C.strict_loads(files["astrachar.json"])
        body = (man.get("body") or {}).get("file")
        settings = (man.get("character") or {}).get("dir")
        parts = CG.parts_of(files, body, settings, strict=False, pack=CG.pack_kind(man))
        return sorted(root for _kind, root in parts), body, files.get(body) if isinstance(body, str) else None
    except Exception:  # noqa: BLE001
        return [], None, None


def bundle_verdict(path: str, raw: bytes, licence) -> dict:
    """Content's verdict on one embedded bundle: {"status": "ok" | "unknown"
    | "bundle", "refusal": {"code", "detail"} | None, "body": (path, bytes) |
    None}. A refusal keeps content's own code; its detail is content's,
    prefixed `<path>!`, so a per-file one reads `<gi path>!<inner path>`."""
    roots, body_path, body = _bundle_layout(raw)
    try:
        got = CG.ingest_bundle(raw, {"declared_licence": roots if licence else []})
    except CG.Refusal as r:
        return {"status": "bundle", "refusal": {"code": r.code, "detail": f"{path}!{r.detail}"}, "body": None}
    except Exception as e:  # noqa: BLE001 -- content's reader raised on a hostile shape: refuse, never crash
        return {"status": "bundle", "body": None, "refusal": {
            "code": "E_CONTENT_FORMAT", "detail": f"{path}!: the content checker cannot read it ({type(e).__name__}: {e})"}}
    status = "unknown" if "F_CONTENT_VRM_META_UNKNOWN" in got["flags"] else "ok"
    return {"status": status, "refusal": None, "body": (body_path, body) if body is not None else None}


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
    except RecursionError:
        # thousands of levels deep: the parser's own stack gives out first, and
        # that is a file this gate refuses, never a crash of the gate itself
        raise GltfFormatError("the glTF JSON does not parse: it nests too deep to read") from None


def _cap_problem(path: str | None, raw: bytes) -> str | None:
    """The content catalogue's own `gltf_problem` (ingest-v1.md §3 step 10):
    a JSON chunk or `.gltf` over 16 MiB, checked BEFORE anything is parsed;
    JSON that does not parse (RecursionError included) or is not an object;
    nesting deeper than 128, the top-level object being depth 1. A duplicate
    member is left to `_strict_json`, which names it."""
    return CG.gltf_problem(path or "", raw)


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
    why = _cap_problem(None, raw)
    if why:
        raise GltfFormatError(f"the GLB's {why}" if why.startswith("its ") else f"the GLB has {why}")
    doc = _strict_json(raw[20:20 + chunk_len])
    if not isinstance(doc, dict):
        raise GltfFormatError("the glTF JSON is not an object")
    return doc


class _AnyFile:
    """`present` when there is no release to look in (a lone file): every
    relative name is taken to exist, so only the shape of the uri is judged."""

    def __contains__(self, _name) -> bool:
        return True


def gltf_uri_problem(raw: bytes, doc: dict, path: str | None, present) -> str | None:
    """No external reference: the content catalogue's own `uri_refusal`
    (ingest-v1.md §3 step 10). In a GLB every `images[].uri` and
    `buffers[].uri` is a `data:` URI; in a `.gltf` each is a `data:` URI or
    a relative path with no scheme, no `..`, no leading `/` and **no `%`,
    `?`, `#` or `\\`** -- a loader percent-decodes (and splits off a query or
    fragment) BEFORE it joins, so `..%2f..%2fetc%2fpasswd` leaves the
    release even when a file with that literal name is in it (N2) -- naming
    a file the release holds (`present`, a set of release-relative paths;
    None skips that last test). Content's own-part test is given no parts:
    a game integration's part is one file, and its buffers are not parts.

    `images` or `buffers` that is not an array is refused here first:
    content's reader skips an object (whose "0" key a JavaScript loader still
    indexes as `images[0]`) and raises on a number."""
    for key in ("images", "buffers"):
        if key in doc and not isinstance(doc[key], list):
            return f"{key} is not an array: {type(doc[key]).__name__}"
    where = present if present is not None and path is not None else _AnyFile()
    return CG.uri_refusal(path or "", raw, where, {})


def gltf_format_problem(raw: bytes, path: str | None = None, present=None) -> str | None:
    """Every GLB (by its magic) and every `.gltf`, in any part and of any
    class: the reason it is `E_CONTENT_FORMAT`, or None. Runs BEFORE
    classification."""
    is_glb = raw[:4] == b"glTF"
    if not is_glb and not (path is not None and path.lower().endswith(".gltf")):
        return None
    if not is_glb:
        # glTF 2.0 is UTF-8 JSON without a byte-order mark: any BOM on a .gltf,
        # UTF-8 or UTF-16/32, is refused by the content catalogue's own rule
        # (N1) -- here, and only for a .gltf (§2.7.1's deliberate difference)
        why = CG.bom_refusal(path, raw) or _cap_problem(path, raw)
        if why:
            return f"a .gltf that {why}" if why.startswith("begins") else why
    try:
        doc = parse_glb_strict(raw) if is_glb else _strict_json(raw)
    except GltfFormatError as e:
        return str(e)
    if not isinstance(doc, dict):
        return "the glTF JSON is not an object"
    return gltf_uri_problem(raw, doc, path, present)


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
    if spath is not None and raw is not None and spath.lower().endswith(BUNDLE_EXTS) and _is_zip(raw[:4]):
        # an embedded bundle: the content contract's own verdict decides; its
        # body's readable VRM licence, when it has one, is the part's licence
        bv = bundle_verdict(spath, raw, entry.get("licence"))
        gate_status, refusal = bv["status"], bv["refusal"]
        if bv["status"] == "ok" and bv["body"] is not None:
            body_gate = vrm_gate(bv["body"][1], bv["body"][0])
            if body_gate["status"] == "ok":
                vrm_licence = body_gate["vrm_licence"]
    if vrm_licence is not None:
        licence_source = "vrm"
    elif entry.get("licence"):
        licence_source = "declared"
    else:
        licence_source = None
    return {"licence_source": licence_source, "vrm_licence": vrm_licence, "gate_status": gate_status, "refusal": refusal}


GATE_CODES = {"refused": "E_CONTENT_LICENCE_REFUSED", "conflict": "E_CONTENT_LICENCE_CONFLICT", "format": "E_CONTENT_FORMAT"}


def _refusal_detail(refusal) -> str:
    if not isinstance(refusal, dict):
        return ""
    if "detail" in refusal:
        return str(refusal["detail"])
    return f"{refusal.get('field')} = {refusal.get('value')!r}"


def release_findings(files: dict[str, bytes], manifest: dict) -> dict:
    """The whole content check of ONE release (manifest.md §2.7), over every
    file it carries -- `files` as `release_files` returns it. Returns
    {"findings": [{"code", "path", "detail"}], "flags": [{"flag", "path"}]};
    any finding refuses the release, a flag publishes it flagged. A part the
    gate refuses is not also asked for its `licence_source`."""
    findings: list[dict] = []
    flags: list[dict] = []
    seen: set = set()

    def refuse(code, path, detail):
        if (code, path) not in seen:
            seen.add((code, path))
            findings.append({"code": code, "path": path, "detail": detail})

    present = set(files)
    # the release's glTF JSON budget, from headers before anything is parsed:
    # the content catalogue's 32 MiB per archive (ingest-v1.md §3 step 5, B1)
    budget = sum(CG.gltf_json_bytes(p, b[:16], len(b)) for p, b in files.items())
    if budget > CG.MAX_GLTF_JSON_TOTAL:
        refuse("E_CONTENT_FORMAT", "", f"{budget} bytes of glTF JSON in the release, over {CG.MAX_GLTF_JSON_TOTAL} (32 MiB)")
    for p, b in sorted(files.items()):
        why = name_problem(p, b)
        if why:
            refuse("E_CONTENT_FORMAT", p, why)
            continue
        # every GLB and every .gltf, declared or not, of any class (§2.7.3)
        why = gltf_format_problem(b, p, present)
        if why:
            refuse("E_CONTENT_FORMAT", p, why)
    found = content_files_of(files)
    cov = content_coverage(manifest, found)
    for p in cov["undeclared"]:
        refuse("E_CONTENT_UNDECLARED", p, "a content-typed file with no [[integration.content]] entry")
    for p in cov["missing"]:
        if ("E_CONTENT_FORMAT", p) not in seen:  # it is there, and refused for what it is
            refuse("E_CONTENT_MISSING", p, "declared, and no content-typed file is at that path")
    for p in cov["duplicates"]:
        refuse("E_CONTENT_DUPLICATE", p, "declared by more than one entry")
    entries = manifest.get("integration", {}).get("content", [])
    for entry in entries if isinstance(entries, list) else []:
        p = entry.get("path") if isinstance(entry, dict) else None
        raw = found.get(p) if isinstance(p, str) else None
        if raw is None:
            continue
        pl = part_licence(entry, raw, present)
        status = pl["gate_status"]
        if status in GATE_CODES:
            refuse(GATE_CODES[status], p, _refusal_detail(pl["refusal"]))
            continue
        if status == "bundle":  # an embedded bundle, refused with the content contract's own code
            refuse(pl["refusal"]["code"], p, pl["refusal"]["detail"])
            continue
        if status == "unknown":
            flags.append({"flag": "F_CONTENT_VRM_META_UNKNOWN", "path": p})
        if pl["licence_source"] is None:
            refuse("E_CONTENT_LICENCE_UNDECLARED", p, "no readable VRM licence and no declared licence")
    return {"findings": findings, "flags": flags}


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
            files = release_files(DATA / v["dir"])
            # too large to commit: built in memory by gen.py, pinned by sha256
            for rel, name in v.get("synth", {}).items():
                raw = gen_module().synth(name)
                report(f"content/releases/{v['name']} synthesised {rel} is the pinned sha256",
                       hashlib.sha256(raw).hexdigest() == v["sha256"][rel])
                files[rel] = raw
            got = release_findings(files, doc)
            codes = sorted({f["code"] for f in got["findings"]})
            flags = sorted({f["flag"] for f in got["flags"]})
            # ONE defect per golden: a refusal carries exactly the code it is named for
            ok = codes == ([v["code"]] if v["verdict"] == "refuse" else [])
            if "detail" in v:
                ok = ok and any(v["detail"] in f["detail"] for f in got["findings"])
            ok = ok and flags == sorted(v.get("flags", []))
            report(f"content/releases/{v['name']}", ok, f"codes={codes} flags={flags} findings={got['findings']}")

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
