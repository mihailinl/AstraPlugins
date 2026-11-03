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

import codecs
import fnmatch
import hashlib
import json
import pathlib
import posixpath
import re
import sys
import time
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


def link_digest(manifest: dict) -> str | None:
    """manifest.md §2.6.1: the consent digest of a GI's `[integration.link]`
    table -- lowercase-hex SHA-256 of the RFC 8785 JCS of the table EXACTLY
    as parsed from the shipped astra-gi.toml (no default added for a key it
    leaves out; key order irrelevant), or None when there is no such table.
    The JCS is spec/content's own (tools/contentlite.py), so this digest and
    every other JCS this repository defines are computed by one function."""
    import hashlib
    link = (manifest.get("integration") or {}).get("link") if isinstance(manifest, dict) else None
    if link is None:
        return None
    return hashlib.sha256(CG.C.jcs(link)).hexdigest()
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
#     one); such a text is instead sniffed as the text it decodes to. That
#     only ever over-refuses: browsers' fetch().text() and three.js decode
#     UTF-8 whatever the mark, so a UTF-16 glTF does not load there at all,
#     and the margin covers a reader that does detect the encoding (Python's
#     json.loads on bytes does);
#   * over 16 MiB the key-by-key sniff is not run (it is a Python loop over
#     every character); a JSON-looking file that large is refused when its
#     bytes name an `asset` key at all -- spelt plainly or with \u escapes,
#     which JSON decodes to the same key -- and accepted otherwise. Nothing
#     that large is a glTF the gate would accept anyway (16 MiB cap, below).

_BOM_CODECS = dict(CG.UNICODE_BOMS)  # content's own mark -> encoding map, UTF-32 first (#132)
_ASSET_KEY = re.compile(rb'"(?:a|\\u0061)(?:s|\\u0073)(?:s|\\u0073)(?:e|\\u0065)(?:t|\\u0074)"')
# ... whose value is an object: three.js reads asset.version, so a glTF's asset is one. A games-only
# difference (manifest.md §2.7.1): {"asset": "textures/hero.png"} is a game's data, not a glTF.
_ASSET_OBJ = re.compile(_ASSET_KEY.pattern + rb"[ \t\r\n]*:[ \t\r\n]*\{")


_HEAD = 64  # bytes decoded at a time while looking for the first character
_CHUNK = 1024 * 1024  # bytes decoded at a time while searching a UTF-16/32 text


def _bom_of(raw: bytes):
    for bom, codec in _BOM_CODECS.items():
        if raw.startswith(bom):
            return bom, codec
    return b"", None


def _decoded_chunks(raw: bytes, size: int):
    """The text as UTF-8, a piece at a time: a UTF-16/32 text decoded by its
    byte-order mark, anything else as it is.
    Never the whole file at once -- a 128 MiB `.pak` that happens to begin
    FF FE once cost 658 MB decoded whole, for a test of its first byte."""
    bom, codec = _bom_of(raw)
    if codec is None:
        for at in range(0, len(raw), size):
            yield raw[at:at + size]
        return
    dec = codecs.getincrementaldecoder(codec)("replace")
    for at in range(len(bom), len(raw), size):
        yield dec.decode(raw[at:at + size]).encode("utf-8")
    yield dec.decode(b"", final=True).encode("utf-8")


def sniff_text(raw: bytes) -> bytes:
    """The whole text, decoded by its byte-order mark, as UTF-8 -- only for
    a file the 16 MiB cap already bounds."""
    bom, codec = _bom_of(raw)
    return raw[len(bom):].decode(codec, "replace").encode("utf-8") if codec else raw


def _first_char(raw: bytes) -> bytes:
    """The first non-whitespace byte of the text (after a UTF-8 BOM), read
    _HEAD bytes at a time: b"" when there is none."""
    first = True
    for piece in _decoded_chunks(raw, _HEAD):
        if first and piece.startswith(CG.UTF8_BOM):
            piece = piece[len(CG.UTF8_BOM):]
        first = first and not piece
        rest = piece.lstrip(b" \t\r\n")
        if rest:
            return rest[:1]
    return b""


def _names_key(raw: bytes, pattern) -> bool:
    """Does the text name the key? At C speed: a UTF-8 file is searched as it
    is, a UTF-16/32 one in decoded chunks that overlap by 4 KiB."""
    if _bom_of(raw)[1] is None:
        return pattern.search(raw) is not None
    tail = b""
    for piece in _decoded_chunks(raw, _CHUNK):
        window = tail + piece
        if pattern.search(window):
            return True
        tail = window[-4096:]
    return False


# The per-character sniff reads at most this much of one release; past it, a
# JSON-looking file whose bytes name an asset key is refused unread, as one
# over 16 MiB is. Without it, twenty 16 MiB files of {"":0,"":0,...} cost the
# gate 102 s (content's sniff reads ~4 MiB a second on them).
SNIFF_BUDGET = 64 * 1024 * 1024


class ReleaseBudget:
    """What one release may make the gate spend: the bytes the per-character
    sniff reads (SNIFF_BUDGET), and the glTF JSON it may parse -- content's
    32 MiB per archive, here per RELEASE, embedded bundles included."""

    def __init__(self):
        self.sniffed = 0
        self.gltf_json = 0


def _json_looking(raw: bytes) -> bool:
    return _first_char(raw) == b"{"


def is_text_gltf(raw: bytes, budget: ReleaseBudget | None = None) -> bool:
    """The content catalogue's text-glTF sniff (`is_gltf_json`, S5/N1), over
    the text decoded by its byte-order mark. First the C-speed test: no
    `asset` key anywhere in the bytes (plain or \\u-escaped) whose value is an
    object is no glTF, and the slow sniff never runs. Above 16 MiB, or once the release's
    SNIFF_BUDGET is spent, the key alone refuses."""
    if not _json_looking(raw) or not _names_key(raw, _ASSET_OBJ):
        return False
    if len(raw) > CG.MAX_GLTF_JSON:
        return True
    budget = budget if budget is not None else ReleaseBudget()
    text = sniff_text(raw)  # bounded: at most 16 MiB of raw bytes
    if budget.sniffed + len(text) > SNIFF_BUDGET:
        return True
    budget.sniffed += len(text)
    return CG.is_gltf_json(text)


def name_problem(path: str, raw: bytes, budget: ReleaseBudget | None = None) -> str | None:
    """Why a file's name and its bytes disagree (E_CONTENT_FORMAT), or None.
    Runs on every file of the release, declared or not."""
    if is_manifest(path):
        return None
    if raw[:4] == CG.GLB_MAGIC:
        # the content catalogue's own name rule, one way: a GLB is named as one
        return None if CG.name_matches_magic(path, raw) else "a GLB (it begins with glTF) named something not .vrm, .glb or .vrma"
    if not path.lower().endswith(".gltf") and is_text_gltf(raw, budget):
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


def _bundle_layout(files: dict[str, bytes]):
    """(part roots, body path, body bytes) by content's own reading of the
    walked files, or ([], None, None) when it cannot read that far --
    `ingest_bundle` then refuses the bundle with the step that failed."""
    try:
        files = {p: b for p, b in files.items() if not p.startswith("\0")}
        man = CG.C.strict_loads(files["astrachar.json"])
        body = (man.get("body") or {}).get("file")
        settings = (man.get("character") or {}).get("dir")
        parts = CG.parts_of(files, body, settings, strict=False, pack=CG.pack_kind(man))
        return sorted(root for _kind, root in parts), body, files.get(body) if isinstance(body, str) else None
    except Exception:  # noqa: BLE001
        return [], None, None


def _ingest_walked(raw: bytes, files: dict[str, bytes], ctx: dict) -> dict:
    """Content's `ingest_bundle` over a bundle ALREADY walked: its own call
    to `walk_zip` is answered with that walk, so a bundle is unzipped once."""
    real = CG.walk_zip
    CG.walk_zip = lambda b: dict(files) if b is raw else real(b)
    try:
        return CG.ingest_bundle(raw, ctx)
    finally:
        CG.walk_zip = real


def bundle_verdict(path: str, raw: bytes, licence, budget: ReleaseBudget | None = None) -> dict:
    """Content's verdict on one embedded bundle: {"status": "ok" | "unknown"
    | "bundle", "refusal": {"code", "detail"} | None, "body": (path, bytes) |
    None}. A refusal keeps content's own code; its detail is content's,
    prefixed `<path>!`, so a per-file one reads `<gi path>!<inner path>`.

    The bundle is unzipped ONCE, by content's walk_zip (whose failure is the
    first failing step ingest_bundle itself would report). Its glTF JSON,
    from the walk's headers, is charged to the release's budget before
    anything in it is parsed: four bundles of 32 MiB each once made the gate
    parse 128 MiB of JSON (787 MB, 31 s) and accepted them."""
    budget = budget if budget is not None else ReleaseBudget()
    try:
        files = CG.walk_zip(raw)
    except CG.Refusal as r:
        return {"status": "bundle", "refusal": {"code": r.code, "detail": f"{path}!{r.detail}"}, "body": None}
    except Exception as e:  # noqa: BLE001 -- content's reader raised on a hostile shape: refuse, never crash
        return {"status": "bundle", "body": None, "refusal": {
            "code": "E_CONTENT_FORMAT", "detail": f"{path}!: the content checker cannot read it ({type(e).__name__}: {e})"}}
    own = sum(CG.gltf_json_bytes(p, b[:16], len(b)) for p, b in files.items() if not p.startswith("\0"))
    if budget.gltf_json + own > CG.MAX_GLTF_JSON_TOTAL:
        return {"status": "bundle", "body": None, "refusal": {"code": "E_CONTENT_FORMAT", "detail":
                f"{path}!: {budget.gltf_json + own} bytes of glTF JSON in the release with this bundle, "
                f"over {CG.MAX_GLTF_JSON_TOTAL} (32 MiB)"}}
    budget.gltf_json += own
    roots, body_path, body = _bundle_layout(files)
    try:
        got = _ingest_walked(raw, files, {"declared_licence": roots if licence else []})
    except CG.Refusal as r:
        return {"status": "bundle", "refusal": {"code": r.code, "detail": f"{path}!{r.detail}"}, "body": None}
    except Exception as e:  # noqa: BLE001 -- content's reader raised on a hostile shape: refuse, never crash
        return {"status": "bundle", "body": None, "refusal": {
            "code": "E_CONTENT_FORMAT", "detail": f"{path}!: the content checker cannot read it ({type(e).__name__}: {e})"}}
    status = "unknown" if "F_CONTENT_VRM_META_UNKNOWN" in got["flags"] else "ok"
    return {"status": status, "refusal": None, "body": (body_path, body) if body is not None else None}


# ── a game's own archives, one level deep (manifest.md §2.7.1) ─────────────
# A zip that is not a content bundle -- a .jar, a mod .zip, detected by its PK
# magic and never by its name -- is opened ONE level deep with the content
# contract's own walk_zip, every cloaking check included, under limits made
# for game archives: 65,536 entries and 512 MiB uncompressed, and no
# Stored-only rule (that is a bundle's). Every GLB, text glTF and bundle in it
# is judged exactly as a top-level file is, and is a part that must be
# DECLARED, as `<archive path>!<inner path>` -- so the per-part rights
# checkbox cannot be bypassed by putting a model in a jar. Cloaking is always
# refused. An archive the walk cannot otherwise open (over the limits, zip64,
# a method it cannot inflate, an encrypted or linked entry, a name content's
# rules refuse, a deflate ratio over 100) is NOT refused: it publishes with
# F_CONTENT_ARCHIVE_UNSCANNED, shown to moderators, so large modpacks still
# work. An archive inside an archive is not opened, and is flagged the same.

CONTAINER_MAX_ENTRIES = 65_536
CONTAINER_MAX_TOTAL = 512 * 1024 * 1024
CLOAK_CODES = ("E_ZIP_HEADERS_INCONSISTENT", "E_ZIP_END_RECORD")
# what a bundle-class file inside an archive is named: these are parts
INNER_PART_EXTS = CG.GLB_EXTS + (".gltf",) + BUNDLE_EXTS


def is_container(path: str, raw: bytes) -> bool:
    """A zip that is not a bundle: by its magic, never by its name."""
    return _is_zip(raw[:4]) and not path.lower().endswith(BUNDLE_EXTS) and not is_bundle_bytes(raw)


def walk_container(raw: bytes) -> dict:
    """{"status": "ok", "files"} | {"status": "unscanned", "reason"} |
    {"status": "refused", "code", "detail"}: content's walk_zip under the
    game-archive limits. Only cloaking -- two readings of one archive -- and
    a glTF JSON total over 32 MiB refuse; any other reason the walk stops is
    an archive this gate could not open."""
    saved = CG.MAX_ENTRIES, CG.MAX_TOTAL, CG.STORED_ONLY
    CG.MAX_ENTRIES, CG.MAX_TOTAL, CG.STORED_ONLY = CONTAINER_MAX_ENTRIES, CONTAINER_MAX_TOTAL, ()
    try:
        files = CG.walk_zip(raw)
    except CG.Refusal as r:
        if r.code in CLOAK_CODES and "zip64" not in r.detail:
            return {"status": "refused", "code": r.code, "detail": r.detail}
        if r.code == "E_ARCHIVE_TOO_LARGE" and "glTF JSON" in r.detail:
            return {"status": "refused", "code": "E_CONTENT_FORMAT", "detail": r.detail}
        return {"status": "unscanned", "reason": f"{r.code}: {r.detail}"}
    except Exception as e:  # noqa: BLE001 -- an archive content's reader cannot follow: fail closed
        return {"status": "refused", "code": "E_CONTENT_FORMAT", "detail": f"the archive cannot be read ({type(e).__name__}: {e})"}
    finally:
        CG.MAX_ENTRIES, CG.MAX_TOTAL, CG.STORED_ONLY = saved
    files.pop("\0order", None)
    return {"status": "ok", "files": {p: b for p, b in files.items() if not p.endswith("/")}}


def is_inner_part(key: str, raw: bytes) -> bool:
    """A GLB, a .gltf or a bundle inside an archive: a part to declare."""
    return key.lower().endswith(INNER_PART_EXTS) and is_content_typed(key, raw)


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
    (ingest-v1.md §3 step 10, with #131). In a GLB every `images[].uri` and
    `buffers[].uri` is a `data:` URI; in a `.gltf` each is a `data:` URI or
    a relative path, percent-decoded exactly once -- `Base%20Color.png`
    names `Base Color.png` -- with no raw `?`, `#` or `\\`, no malformed or
    double escape, and once decoded no scheme, no `..` and no leading `/`,
    naming a file the release holds (`present`, a set of release-relative
    paths; None skips that last test). `images`/`buffers` must be arrays of
    objects (content's `gltf_array_shape_refusal`). Content's own-part test is
    given no parts: a game integration's part is one file, and its buffers
    are not parts. `doc` is unused since content reads `raw` itself; it is
    kept for the callers' signature."""
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
        # (N1, narrowed by #132 to text kinds) -- called here for a .gltf ONLY:
        # content also refuses a UTF-16 .json or .toml, which a game
        # integration ships as localisation (§2.7.1's deliberate difference)
        why = CG.bom_refusal(path, raw) or _cap_problem(path, raw)
        if why:
            return why
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


def part_licence(entry: dict, raw, present=None, budget: ReleaseBudget | None = None) -> dict:
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
        bv = bundle_verdict(spath, raw, entry.get("licence"), budget)
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
    budget = ReleaseBudget()
    # the release's glTF JSON budget, from headers before anything is parsed:
    # the content catalogue's 32 MiB per archive (ingest-v1.md §3 step 5, B1)
    budget.gltf_json = sum(CG.gltf_json_bytes(p, b[:16], len(b)) for p, b in files.items())
    if budget.gltf_json > CG.MAX_GLTF_JSON_TOTAL:
        refuse("E_CONTENT_FORMAT", "", f"{budget.gltf_json} bytes of glTF JSON in the release, over {CG.MAX_GLTF_JSON_TOTAL} (32 MiB)")
    found = content_files_of(files)
    present_of: dict[str, set] = {}  # an inner part's archive, for its .gltf's relative uris
    for p, b in sorted(files.items()):
        why = name_problem(p, b, budget)
        if why:
            refuse("E_CONTENT_FORMAT", p, why)
            continue
        # every GLB and every .gltf, declared or not, of any class (§2.7.3)
        why = gltf_format_problem(b, p, present)
        if why:
            refuse("E_CONTENT_FORMAT", p, why)
            continue
        if not is_container(p, b):
            continue
        walked = walk_container(b)
        if walked["status"] == "refused":
            refuse(walked["code"], p, walked["detail"])
            continue
        if walked["status"] == "unscanned":
            flags.append({"flag": "F_CONTENT_ARCHIVE_UNSCANNED", "path": p, "detail": walked["reason"]})
            continue
        inner = {f"{p}!{q}": data for q, data in walked["files"].items()}
        own = sum(CG.gltf_json_bytes(k, d[:16], len(d)) for k, d in inner.items())
        if budget.gltf_json + own > CG.MAX_GLTF_JSON_TOTAL:
            refuse("E_CONTENT_FORMAT", p, f"{budget.gltf_json + own} bytes of glTF JSON in the release with this "
                                          f"archive, over {CG.MAX_GLTF_JSON_TOTAL} (32 MiB)")
            continue
        budget.gltf_json += own
        inner_present = set(inner)
        for k, d in sorted(inner.items()):
            if k in files:  # a top-level file literally named like this member: two parts, one path
                refuse("E_CONTENT_FORMAT", k, "a file named like a member of an archive beside it")
                continue
            why = name_problem(k, d, budget) or gltf_format_problem(d, k, inner_present)
            if why:
                refuse("E_CONTENT_FORMAT", k, why)
                continue
            if _is_zip(d[:4]) and not k.lower().endswith(BUNDLE_EXTS):
                flags.append({"flag": "F_CONTENT_ARCHIVE_UNSCANNED", "path": k,
                              "detail": "an archive inside an archive: opened one level deep"})
                continue
            if is_inner_part(k, d):
                found[k] = d
                present_of[k] = inner_present
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
        pl = part_licence(entry, raw, present_of.get(p, present), budget)
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
    if re.search(r"~[0-9]", c):
        # An 8.3 short name (XINPUT~1.DLL, PROGRA~1): a direct lookup
        # resolves it to some other file, a proxy under a name no list knows.
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
    """§7.4, exactly: no `chain` and no `via-manager` strategy in `coexist`,
    and no `tell` in any strategy. A passive loader never makes Astra load,
    tell or route anything."""
    co = loader.get("coexist")
    return isinstance(co, list) and all(
        isinstance(s, dict) and s.get("strategy") not in ("chain", "via-manager") and "tell" not in s for s in co)


def detection_patterns(doc: dict) -> list[str]:
    """§7.4: the last component of every name this descriptor's OWN
    detection rules look up (`listed`, `child`, `stat`, `tail`, a bootstrap's
    `listed`, an `also_if` `dir`), lower-cased, with each placeholder read as
    `*`. A name that is nothing but placeholders and wildcards (`{program}`)
    is the program itself, which the program rule already covers."""
    out, stack = [], [doc.get("rule")]
    while stack:
        v = stack.pop()
        if isinstance(v, dict):
            for k in ("listed", "child", "stat", "tail", "dir"):
                if isinstance(v.get(k), str):
                    last = _PLACEHOLDER.sub("*", v[k].rsplit("/", 1)[-1]).lower()
                    if last.replace("*", ""):
                        out.append(last)
            stack.extend(v.values())
        elif isinstance(v, list):
            stack.extend(v)
    return out


def _detection_name(path: str, doc: dict) -> bool:
    last = path.rsplit("/", 1)[-1].lower()
    return any(fnmatch.fnmatchcase(last, pattern) for pattern in detection_patterns(doc))


def _file_anchors(loader: dict, doc: dict) -> list[str]:
    """§7.4: top-level `file` lookups whose last component holds a literal
    name that is not a proxy, not a ubiquitous runtime, not the game's own
    program and not a name this descriptor's detection looks up."""
    return [p for p in _top_lookups(loader, "file")
            if _anchor_name(p) and not _proxy_or_runtime(p) and not _program_shaped(p)
            and not _detection_name(p, doc)]


def _root_anchored(loader: dict, doc: dict) -> bool:
    """§7.4: anchored on its root -- no file anchor, and a top-level `child`
    or `stat` of kind `dir` of exactly its own `root` (never `listed`: a
    folder is named by the two lookups that name one)."""
    req = loader.get("require")
    roots = [e for e in req if isinstance(e, dict)] if isinstance(req, list) else []
    return not _file_anchors(loader, doc) and any(
        e.get("kind") == "dir" and isinstance(e.get(k), str) and e[k] == loader.get("root")
        and _anchor_name(e[k]) and not _detection_name(e[k], doc)
        for e in roots for k in ("child", "stat") if k in e)


def rule_mods_loader_anchor_invalid(doc: dict) -> bool:
    """True = OK. §7.4: every loader is anchored -- by a file, or on its own
    root. Whether a root-anchored loader may be so is the next rule's."""
    return all(_file_anchors(l, doc) or _root_anchored(l, doc) for l in mods_loaders(doc))


def rule_mods_root_anchor_not_passive(doc: dict) -> bool:
    """True = OK. §7.4: a root-anchored loader is passive. One that also
    declares `chain` or a `tell` is refused, so that a later member can never
    quietly make a root-anchored loader active: an active loader needs a
    file anchor."""
    return all(_passive(l) for l in mods_loaders(doc) if _root_anchored(l, doc))


def rule_mods_chain_entry_invalid(doc: dict) -> bool:
    """True = OK. §7.6: a `chain` entry is a `.dll`, and one of the loader's
    own top-level `file` lookups -- a file its recognition already found --
    and never a proxy, a ubiquitous runtime, the game's own program or a
    name this descriptor's detection looks up."""
    for loader in mods_loaders(doc):
        own = set(_top_lookups(loader, "file"))
        for s in loader.get("coexist", []) if isinstance(loader.get("coexist"), list) else []:
            if not isinstance(s, dict) or s.get("strategy") != "chain" or not isinstance(s.get("entry"), str):
                continue
            e = s["entry"]
            if e not in own or _proxy_or_runtime(e) or _program_shaped(e) or _detection_name(e, doc) \
                    or not e.lower().endswith(".dll"):
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


def rule_mods_version_unreadable(doc: dict) -> bool:
    """True = OK. §7.4: every `versions` operand reads in its template's
    shape (`>=a.b`, or `>=1.2.3` on a two-run template, does not). A
    template or `versions` the schema already refuses is the schema's."""
    for loader in mods_loaders(doc):
        v = loader.get("version")
        if not isinstance(v, dict) or not isinstance(v.get("template"), str) or not isinstance(v.get("versions"), str):
            continue
        if not _TEMPLATE.match(v["template"]) or not _VERSIONS.match(v["versions"]):
            continue
        if any(read_operand(v["template"], operand) is None for _op, operand in version_comparators(v["versions"])):
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
    "mods-version-unreadable": rule_mods_version_unreadable,
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
    "mods-version-unreadable": "version-invalid",
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
    want = (v.get("rules") or [v["rule"]]) if v["check"] == "semantic" else []
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
            files = release_files(DATA / v["dir"])
            # too large to commit: built in memory by gen.py, pinned by sha256
            for rel, name in v.get("synth", {}).items():
                raw = gen_module().synth(name)
                report(f"content/releases/{v['name']} synthesised {rel} is the pinned sha256",
                       hashlib.sha256(raw).hexdigest() == v["sha256"][rel])
                files[rel] = raw
            started = time.monotonic()
            if "max_peak_mib" in v:  # a memory bound, measured around the check alone
                import tracemalloc
                tracemalloc.start()
            got = release_findings(files, doc)
            if "max_peak_mib" in v:
                peak = tracemalloc.get_traced_memory()[1] / (1024 * 1024)
                tracemalloc.stop()
                report(f"content/releases/{v['name']} within {v['max_peak_mib']} MiB", peak <= v["max_peak_mib"], f"{peak:.0f} MiB")
            if "max_seconds" in v:  # a cost bound: the gate must not be made to spend more on this release
                spent = time.monotonic() - started
                report(f"content/releases/{v['name']} within {v['max_seconds']} s", spent <= v["max_seconds"], f"{spent:.1f} s")
            if v.get("guard") == "strict_json":
                # content's gltf_problem meets a too-deep JSON first and catches its
                # RecursionError, so the verdict above cannot see games' own guard: run
                # the golden through games' strict parser alone, which must refuse it
                for rel, raw in sorted(files.items()):
                    if rel.endswith(".gltf"):
                        try:
                            _strict_json(raw)
                            held = False
                        except GltfFormatError:
                            held = True
                        except RecursionError:
                            held = False
                        report(f"content/releases/{v['name']} {rel} refused by _strict_json alone, never a crash", held)
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
    for v in vectors["link"].get("digest", []):
        if v.get("crlf"):
            # the golden only tests normalisation while it really holds CRLF
            raw = (DATA / v["manifest"]).read_bytes()
            report(f"link/digest/{v['name']} holds CRLF", b"\r\n" in raw)
        got = link_digest(load_doc(v["manifest"]))
        report(f"link/digest/{v['name']}", got == v["digest"], f"{got} vs {v['digest']}")
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
