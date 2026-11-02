#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Minice — https://minice.ai
"""Writes every golden under testdata/content/ except README.md, vectors.json
and this file. NEVER hand-edit a generated golden: change this script, re-run
it, commit both. `--check` regenerates into memory and fails on any byte that
differs from the tree or from SHA256SUMS (the `content-spec` CI job runs it).

Deterministic by construction: fixed zip timestamps, no compression level
left to the library's default (zlib level 9, raw deflate), Ed25519 is
deterministic, the TEST keys come from fixed published seeds
(tools/contentlite.py `test_seed`) and JSON is written by one function.

The verdicts are NOT here. testdata/content/vectors.json says, by hand, what
each golden must be refused with; tools/check-content-goldens.py derives the
verdict from the bytes and compares. A generator bug that produces the wrong
file therefore turns the checker red instead of agreeing with itself.

    python3 testdata/content/gen.py           # write
    python3 testdata/content/gen.py --check   # exit 1 on drift
"""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import struct
import sys
import zlib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import contentlite as C  # noqa: E402

KINDS = ["commands", "characters", "models", "animsets", "packs"]
KEY_KINDS = KINDS + ["games"]
T0 = 1798675200  # 2026-12-31T00:00:00Z, the goldens' "now" unless a vector says otherwise
WEEK = 7 * 86400
CURRENT_NB = "2026-10-01T00:00:00Z"
NEXT_NB = "2026-12-01T00:00:00Z"
NOV15 = 1794700800  # 2026-11-15T00:00:00Z: after current's not_before, before next's

OUT: dict[str, bytes] = {}


def put(rel: str, data: bytes | str) -> None:
    if isinstance(data, str):
        data = data.encode("utf-8")
    assert rel not in OUT, rel
    OUT[rel] = data


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ── keys ─────────────────────────────────────────────────────────────────

def key(name: str) -> tuple[bytes, str]:
    seed = C.test_seed(name)
    return seed, C.b64(C.public_key(seed))


ROOT_KEY = "astra-root-test"
INDEX_KEY = "astra-index-test"


def kind_key_id(kind: str, role: str) -> str:
    return f"astra-{kind}-2026{'a' if role == 'current' else 'b'}"


def kind_keys_rows() -> list[dict]:
    rows = []
    for k in KEY_KINDS:
        for role, nb in (("current", CURRENT_NB), ("next", NEXT_NB)):
            kid = kind_key_id(k, role)
            rows.append({"kind": k, "role": role, "key_id": kid, "alg": "ed25519",
                         "public_key": key(kid)[1], "not_before": nb})
    return rows


def index_keys_rows() -> list[dict]:
    return [{"key_id": INDEX_KEY, "public_key": key(INDEX_KEY)[1],
             "not_before": "2026-07-01T00:00:00Z", "not_after": "2027-07-01T00:00:00Z", "comment": "TEST"}]


def envelope(domain: str, signed: dict, signer, sign_domain: str | None = None,
             comment: str | None = None) -> dict:
    """`signer`: one key id, a list of them (one signature each, in that order), or None."""
    env: dict = {}
    if comment:
        env["$comment"] = comment
    env["signed"] = signed
    sigs = []
    for one in ([] if signer is None else [signer] if isinstance(signer, str) else signer):
        seed, _ = key(one)
        digest = C.signing_digest(sign_domain or domain, signed)
        sigs.append({"key_id": one, "sig": C.b64(C.sign(seed, digest))})
    env["signatures"] = sigs
    return env


def put_json(rel: str, doc) -> None:
    put(rel, C.pretty(doc))


# ── raw zip writer (hostile shapes need control the stdlib does not give) ─

DOS_TIME, DOS_DATE = 0, (2026 - 1980) << 9 | 1 << 5 | 1


# ── a pure-Python raw-DEFLATE (RFC 1951) encoder ──────────────────────────
#
# `deflate()` MUST NOT depend on which zlib the interpreter links: CI (stock
# zlib, Python 3.12) and every workstation here (zlib-ng, Python 3.14)
# compress the same bytes differently, which turned every golden built with
# `zlib.compressobj` into a coin flip (content-spec red on #127/c596522,
# "DRIFT: archives/hostile/gltf-json-utf16.astrapack, SHA256SUMS"). This
# encoder is a closed function of its input: fixed-Huffman blocks (BTYPE=01,
# RFC 1951 §3.2.6) over a deterministic greedy LZ77 parse. `zlib.crc32` stays
# (a CRC is a pure function with one answer); `zlib.compress`/`compressobj`
# and `zipfile`'s DEFLATED writer must never appear here again — see the
# guard in tools/test_check_content_goldens.py.
#
# LZ77 parse, one pass, left to right:
#   * a 3-byte rolling hash keyes a chain of every earlier position sharing
#     that 3-byte prefix, within the 32 KiB window RFC 1951 allows;
#   * at each position, distance 1 is tried FIRST and extended directly
#     (byte-for-byte against data[pos-1]) before any chain walk — this is
#     the fast path for the long single-byte runs the goldens actually use
#     (`ratio-bomb.astrachar`'s 1 MiB of `\x00`), and it is what keeps
#     `gen.py --check` well under the ~2 minute budget: a chain walk alone
#     would re-hash and re-compare the whole run byte by byte, while the
#     distance-1 path finds the maximum 258-byte match in one scan and the
#     position jumps straight past it;
#   * failing that, the hash chain for the current 3-byte key is walked
#     newest-first, capped at MAX_CHAIN candidates, keeping the longest
#     match found (ties keep the first — i.e. nearest/most-recent — match,
#     because the walk is newest-first and only a strictly longer match
#     replaces it);
#   * a match shorter than MIN_MATCH (3) is not emitted; the byte is a
#     literal instead. A match or literal both insert the current position
#     into the hash chain for its own key (skipped positions inside a match
#     are not separately hashed — fewer candidates, but the encoder only
#     has to be correct and deterministic, not optimal).
#
# Every Huffman code (literal/length and distance) is written bit (length-1)
# down to bit 0 — DEFLATE packs Huffman codes most-significant-bit first,
# unlike every other field (lengths, extra bits), which is least-significant
# bit first. Mixing the two up is the classic way to write a decoder-shaped
# bug that only a real `zlib.decompress` catches, which is why the self-test
# below decompresses every sample instead of trusting the encoder's own math.

_LENGTH_BASE = (3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59,
                67, 83, 99, 115, 131, 163, 195, 227, 258)
_LENGTH_EXTRA_BITS = (0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3,
                      4, 4, 4, 4, 5, 5, 5, 5, 0)
_DIST_BASE = (1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769,
              1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577)
_DIST_EXTRA_BITS = (0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8,
                    9, 9, 10, 10, 11, 11, 12, 12, 13, 13)
_MIN_MATCH = 3
_MAX_MATCH = 258
_WINDOW = 32768
_MAX_CHAIN = 128


def _length_code(length: int) -> tuple[int, int, int]:
    for i in range(len(_LENGTH_BASE) - 1, -1, -1):
        if length >= _LENGTH_BASE[i]:
            return 257 + i, _LENGTH_EXTRA_BITS[i], length - _LENGTH_BASE[i]
    raise ValueError(length)


def _dist_code(dist: int) -> tuple[int, int, int]:
    for i in range(len(_DIST_BASE) - 1, -1, -1):
        if dist >= _DIST_BASE[i]:
            return i, _DIST_EXTRA_BITS[i], dist - _DIST_BASE[i]
    raise ValueError(dist)


def _fixed_litlen_code(v: int) -> tuple[int, int]:
    """RFC 1951 §3.2.6's explicit formulas for the fixed literal/length tree."""
    if v <= 143:
        return v + 0x30, 8
    elif v <= 255:
        return v - 144 + 0x190, 9
    elif v <= 279:
        return v - 256, 7
    else:
        return v - 280 + 0xC0, 8


class _BitWriter:
    def __init__(self) -> None:
        self.out = bytearray()
        self._cur = 0
        self._n = 0

    def _push(self, bit: int) -> None:
        self._cur |= (bit & 1) << self._n
        self._n += 1
        if self._n == 8:
            self.out.append(self._cur)
            self._cur = 0
            self._n = 0

    def bits_lsb(self, value: int, n: int) -> None:
        """Ordinary DEFLATE fields: least-significant bit first."""
        for i in range(n):
            self._push((value >> i) & 1)

    def huffman(self, code: int, length: int) -> None:
        """A Huffman code: most-significant bit first."""
        for i in range(length - 1, -1, -1):
            self._push((code >> i) & 1)

    def finish(self) -> bytes:
        if self._n:
            self.out.append(self._cur)
            self._cur = 0
            self._n = 0
        return bytes(self.out)


def _find_match(data: bytes, pos: int, chains: dict[bytes, list[int]]) -> tuple[int, int]:
    n = len(data)
    limit = min(_MAX_MATCH, n - pos)
    if limit < _MIN_MATCH:
        return 0, 0
    # distance-1 fast path: the common case (long single-byte runs) in one
    # scan, with no hash lookup and no chain walk.
    best_len, best_dist = 0, 0
    if pos > 0 and data[pos] == data[pos - 1]:
        length = 1
        while length < limit and data[pos + length] == data[pos - 1]:
            length += 1
        if length >= _MIN_MATCH:
            best_len, best_dist = length, 1
            if best_len >= limit:
                return best_len, best_dist
    key = data[pos:pos + 3]
    cands = chains.get(key)
    if cands:
        tried = 0
        for cpos in reversed(cands):
            dist = pos - cpos
            if dist <= 0:
                continue
            if dist > _WINDOW:
                break  # chains are append-only/oldest-first, so nothing further back fits either
            tried += 1
            if tried > _MAX_CHAIN:
                break
            length = 0
            while length < limit and data[cpos + length] == data[pos + length]:
                length += 1
            if length > best_len:
                best_len, best_dist = length, dist
                if best_len >= limit:
                    break
    if best_len >= _MIN_MATCH:
        return best_len, best_dist
    return 0, 0


def deflate(data: bytes) -> bytes:
    """Raw DEFLATE (no zlib wrapper, matching `zlib.decompressobj(-15)`), one
    fixed-Huffman final block, built by a deterministic pure-Python LZ77 —
    see the block comment above. Depends on nothing but `data`."""
    bw = _BitWriter()
    bw.bits_lsb(1, 1)  # BFINAL
    bw.bits_lsb(1, 2)  # BTYPE = 01 (fixed Huffman)

    n = len(data)
    chains: dict[bytes, list[int]] = {}
    pos = 0
    while pos < n:
        length, dist = _find_match(data, pos, chains)
        if length >= _MIN_MATCH:
            code, ebits, eval_ = _length_code(length)
            huff, hlen = _fixed_litlen_code(code)
            bw.huffman(huff, hlen)
            if ebits:
                bw.bits_lsb(eval_, ebits)
            dcode, debits, deval = _dist_code(dist)
            bw.huffman(dcode, 5)
            if debits:
                bw.bits_lsb(deval, debits)
            if n - pos >= 3:
                chains.setdefault(data[pos:pos + 3], []).append(pos)
            pos += length
        else:
            huff, hlen = _fixed_litlen_code(data[pos])
            bw.huffman(huff, hlen)
            if n - pos >= 3:
                chains.setdefault(data[pos:pos + 3], []).append(pos)
            pos += 1

    huff, hlen = _fixed_litlen_code(256)  # end-of-block
    bw.huffman(huff, hlen)
    return bw.finish()


# A fixed vector: this exact input must produce this exact output. Any change
# to the encoder above that changes a single bit makes this assertion fail,
# which is the point — it is the generator's own golden.
_VECTOR_INPUT = b"the quick brown fox jumps over the lazy dog. the quick brown fox."
_VECTOR_OUTPUT_HEX = (
    "2bc94855282ccd4cce56482aca2fcf5348cbaf50c82acd2d2856c82f4b2d520"
    "049e72456552aa4e4a7eb8179688af500"
)


def _self_test_deflate() -> None:
    """Round-trips varied inputs through `zlib.decompress(…, -15)` and checks
    the fixed vector. Run on every `gen.py` invocation: a wrong encoder must
    never reach a committed golden."""
    import random
    rng = random.Random(0)
    samples = [
        b"", b"a", b"ab", b"abc", b"\x00", b"\x00" * 2, b"\x00" * 3,
        b"\x00" * 257, b"\x00" * 258, b"\x00" * 259, b"\x00" * 1024,
        b"\x00" * (1024 * 1024),
        bytes(range(256)) * 10,
        b"the quick brown fox jumps over the lazy dog " * 50,
        bytes(rng.randrange(256) for _ in range(4000)),
        _VECTOR_INPUT,
    ]
    for sample in samples:
        comp = deflate(sample)
        got = zlib.decompress(comp, -15)
        assert got == sample, f"deflate() self-test failed to round-trip {sample[:40]!r}"
    vector = deflate(_VECTOR_INPUT)
    assert vector.hex() == _VECTOR_OUTPUT_HEX, (
        f"deflate() fixed vector changed: got {vector.hex()!r}, want {_VECTOR_OUTPUT_HEX!r}")


_self_test_deflate()


def zip_bytes(entries: list[dict], tail: bytes = b"", eocd_override=None, cd_order=None) -> bytes:
    """entries: {name, data, method=0|8, ext_attr, flags, local_name, extra}."""
    out = bytearray()
    central = bytearray()
    offsets: list[int] = []
    for e in entries:
        if "alias_of" in e:  # a second directory entry for an EARLIER local header: an overlap
            src = entries[e["alias_of"]]
            nm = e.get("name", src["name"]).encode("utf-8")
            data = src.get("data", b"")
            comp = deflate(data) if src.get("method", 0) == 8 else data
            central += struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, (3 << 8) | 20, 20, 0, src.get("method", 0),
                                   DOS_TIME, DOS_DATE, zlib.crc32(data) & 0xFFFFFFFF, len(comp), len(data), len(nm),
                                   0, 0, 0, 0, 0o100644 << 16, offsets[e["alias_of"]])
            central += nm
            offsets.append(offsets[e["alias_of"]])
            continue
        out += e.get("pad_before", b"")
        offsets.append(len(out))
        name = e["name"].encode("utf-8")
        local_name = e.get("local_name", e["name"]).encode("utf-8")
        data = e.get("data", b"")
        method = e.get("method", 0)
        comp = deflate(data) if method == 8 else data
        crc = zlib.crc32(data) & 0xFFFFFFFF
        flags = e.get("flags", 0) | (0x800 if any(c > 0x7F for c in name) else 0)
        extra = e.get("extra", b"")
        off = len(out)
        dd = e.get("dd")  # a bit-3 data descriptor: {sig, crc, central_bit3, local_sizes}
        lflags, cflags, lcrc, lcs, lus = flags, flags, crc, len(comp), len(data)
        if dd is not None:
            lflags |= 0x8
            cflags |= 0x8 if dd.get("central_bit3", True) else 0
            if not dd.get("local_sizes", False):
                lcrc, lcs, lus = 0, 0, 0
        lextra = e.get("local_extra", extra)  # a field in the LOCAL header only
        out += struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, lflags, method, DOS_TIME, DOS_DATE,
                           lcrc, lcs, lus, len(local_name), len(lextra))
        out += local_name + lextra + comp
        if dd is not None:
            out += (b"PK\x07\x08" if dd.get("sig", True) else b"") + struct.pack(
                "<III", dd.get("crc", crc), len(comp), len(data))
        flags = cflags
        central += struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, e.get("made_by", (3 << 8) | 20), 20, flags, method,
                               DOS_TIME, DOS_DATE, crc, len(comp), len(data), len(name), len(extra), 0,
                               0, 0, e.get("ext_attr", 0o100644 << 16), off)
        central += name + extra
    if cd_order is not None:  # the directory in another order than the local headers
        recs = []
        q = 0
        while q < len(central):
            nl, xl, cl = struct.unpack("<HHH", central[q + 28:q + 34])
            recs.append(bytes(central[q:q + 46 + nl + xl + cl]))
            q += 46 + nl + xl + cl
        central = bytearray(b"".join(recs[i] for i in cd_order))
    cd_off = len(out)
    out += central
    n = len(entries)
    if eocd_override is not None:
        n_disk, n_total, cd_size, cd_offset = eocd_override(n, len(central), cd_off)
    else:
        n_disk, n_total, cd_size, cd_offset = n, n, len(central), cd_off
    out += struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, n_disk, n_total, cd_size, cd_offset, 0)
    return bytes(out) + tail


# ── GLB / VRM ────────────────────────────────────────────────────────────

def glb(gltf: dict) -> bytes:
    j = json.dumps(gltf, separators=(",", ":"), sort_keys=True).encode("utf-8")
    j += b" " * (-len(j) % 4)
    body = struct.pack("<I4s", len(j), b"JSON") + j
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


def vrm1(meta: dict | None) -> bytes:
    g: dict = {"asset": {"version": "2.0"}}
    if meta is not None:
        g["extensions"] = {"VRMC_vrm": {"specVersion": "1.0", "meta": meta}}
        g["extensionsUsed"] = ["VRMC_vrm"]
    return glb(g)


VRM1_ALLOWED = {
    "name": "Aiko", "version": "1.0", "authors": ["test-author"],
    "licenseUrl": "https://vrm.dev/licenses/1.0/",
    "avatarPermission": "everyone", "allowRedistribution": True,
    "commercialUsage": "personalProfit", "creditNotation": "required", "modification": "allowModification",
    "allowExcessivelyViolentUsage": False, "allowExcessivelySexualUsage": False,
    "allowPoliticalOrReligiousUsage": False, "allowAntisocialOrHateUsage": False,
}
VRM0_ALLOWED = {
    "title": "Aiko", "version": "1.0", "author": "test-author",
    "allowedUserName": "Everyone", "licenseName": "CC_BY",
    "violentUssageName": "Disallow", "sexualUssageName": "Disallow", "commercialUssageName": "Allow",
}


def vrm_both(meta0: dict, meta1: dict) -> bytes:
    return glb({"asset": {"version": "2.0"},
                "extensions": {"VRM": {"meta": meta0}, "VRMC_vrm": {"specVersion": "1.0", "meta": meta1}},
                "extensionsUsed": ["VRM", "VRMC_vrm"]})


# ── character / animset bundles (astra-companion docs/character-files.md) ─

def manifest(fmt: str, kind: str, files: dict[str, bytes], body: str | None) -> bytes:
    m = {
        "format": fmt, "format_version": 1, "needs": [], "schema": 5,
        "generator": "testdata/content/gen.py", "kind": kind,
        "character": {"id": "aiko", "name": "Aiko", "dir": "characters/aiko"},
        "body": {"file": body} if body else None,
        "packs": [], "accessories": [], "builtins": {},
        "files": {p: {"sha256": "sha256:" + sha(b), "size": len(b)} for p, b in sorted(files.items())},
        "excluded": [],
    }
    return json.dumps(m, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8") + b"\n"


def bundle_entries(fmt: str, files: dict[str, bytes], body: str | None = None, kind: str = "vrm",
                   methods: dict[str, int] | None = None, listed: dict[str, bytes] | None = None,
                   tweak=None, manifest_last: bool = True) -> list[dict]:
    methods = methods or {}
    entries = [{"name": p, "data": b, "method": methods.get(p, 0 if p.endswith((".vrm", ".glb", ".png")) else 8)}
               for p, b in sorted(files.items())]
    man = {"name": "astrachar.json", "data": manifest(fmt, kind, listed if listed is not None else files, body),
           "method": 8}
    if manifest_last:
        entries.append(man)
    else:
        entries.insert(0, man)
    if tweak:
        entries = tweak(entries)
    return entries


def bundle(*a, **kw) -> bytes:
    return zip_bytes(bundle_entries(*a, **kw))


# ── part-digest goldens (part-digest-v1.md §4) ───────────────────────────

# paths relative to the PART ROOT (part-digest-v1.md §2): a pack's own directory
ASCII_PART = {
    "animpack.toml": b'name = "wave"\n',
    "clips/a.fbx": b"FBX-A",
    "clips/b.fbx": b"FBX-B",
}
NONASCII_PART = {"clips/ü.fbx": "OGG-FBX-ü-body".encode("utf-8")}
SINGLE_FILE = b"glTF-VRM-test"  # the single-file vector agreed with astra-companion-5f: path ""


def in_pack(pack_id: str, files: dict[str, bytes]) -> dict[str, bytes]:
    """The same pack as it sits inside a .astrachar: under animpacks/<id>/."""
    return {f"animpacks/{pack_id}/{p}": b for p, b in files.items()}


def gen_part_digest() -> None:
    for name, files in (("ascii", ASCII_PART), ("non-ascii", NONASCII_PART)):
        for p, b in files.items():
            put(f"part-digest/{name}/{p}", b)
        put(f"part-digest/{name}.jcs", C.jcs(C.part_digest_pairs(files, root="")))
    put("part-digest/single-file/body.vrm", SINGLE_FILE)
    put("part-digest/single-file.jcs", C.jcs(C.part_digest_pairs({"body.vrm": SINGLE_FILE}, root=None)))


# ── the items the valid documents describe ───────────────────────────────

BODY_PATH = "characters/aiko/body.vrm"
BODY = vrm1(VRM1_ALLOWED)
MODEL_FILES = {BODY_PATH: BODY}
MODEL_PART = C.part_digest(MODEL_FILES, root=None)  # a lone .vrm body: one pair, path ""
ANIMSET_PART = C.part_digest(ASCII_PART, root="")  # == 5cbec44c…f255, the §4 ASCII golden
CHAR_FILES = {"characters/aiko/character.toml": b'name = "Aiko"\nmodel = "aiko-body"\n'}

LISTING = {"en": {"title": "Aiko", "description": "A test character."},
           "ru": {"title": "Айко", "description": "Тестовый персонаж."}}
THUMB = b"\x89PNG\r\n\x1a\n" + b"TEST-THUMBNAIL"
THUMBNAIL = {"sha256": sha(THUMB), "size": len(THUMB)}
UNKNOWN_USAGE = {"violent": "unknown", "sexual": "unknown", "political": "unknown", "antisocial": "unknown"}
DECLARED_CC_BY = {
    "source": "declared", "spec": "none", "commercial_detail": None, "redistribution": "allowed",
    "avatar_permission": "unknown", "modification": "allowed", "commercial": "allowed", "credit_required": True,
    "spdx": "CC-BY-4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/", "usage": UNKNOWN_USAGE,
}
VRM1_LICENCE = {
    "source": "vrm", "spec": "vrm1", "commercial_detail": "personalProfit", "redistribution": "allowed",
    "avatar_permission": "everyone", "modification": "allowed", "commercial": "allowed", "credit_required": True,
    "spdx": None, "license_url": "https://vrm.dev/licenses/1.0/",
    "usage": {"violent": "prohibited", "sexual": "prohibited", "political": "prohibited", "antisocial": "prohibited"},
}
CREDITS = [{"name": "test-author", "role": "model", "url": "https://example.invalid/test-author"}]


def gen_bundles() -> dict[str, bytes]:
    b = {}
    b["model"] = bundle("astra.character", MODEL_FILES, body=BODY_PATH)
    b["animset"] = bundle("astra.animpack", ASCII_PART, body=None, kind="vrm")
    b["character"] = bundle("astra.character", CHAR_FILES, body=None)
    put("archives/valid/model-aiko.astrachar", b["model"])
    put("archives/valid/animset-wave.astrapack", b["animset"])
    put("archives/valid/character-aiko.astrachar", b["character"])
    # the SAME pack inside a .astrachar, under an id that varies per machine: one digest (§4)
    put("archives/valid/character-with-pack.astrachar",
        bundle("astra.character", {**CHAR_FILES, **in_pack("moves (2)", ASCII_PART)}, body=None))
    return b


# ── commands (the client's CommandDefinition JSON, the fields the extractor reads) ─

def command(cid: str, name: str, triggers=None, actions=None, workflow=None) -> dict:
    d = {"id": cid, "name": name, "triggers": triggers or [], "actions": actions or [], "enabled": True}
    if workflow is not None:
        d["workflow"] = workflow
    return d


def node(nid, node_type, data=None):
    return {"id": nid, "node_type": node_type, "data": data or {}}


def graph(*nodes, edges=None):
    return {"nodes": {n["id"]: n for n in nodes}, "edges": edges or {}}


UUID = "00000000-0000-4000-8000-0000000000"

COMMANDS = {
    # valid
    "greet": command(UUID + "01", "Greet", [{"type": "text", "phrases": ["hello astra"]}],
                     [{"type": "speak", "text": "Hello!"}, {"type": "send_to_ai", "prompt": "Say hi"}]),
    "build-and-ask": command(UUID + "02", "Build and ask",
                             [{"type": "hotkey", "modifiers": ["ctrl", "alt"], "key": "b"}],
                             [{"type": "execute", "command": "make"},
                              {"type": "send_to_ai", "prompt": "What failed?"}]),
    "roll-dice": command(UUID + "03", "Roll dice", workflow=graph(
        node("t", "trigger", {"trigger_type": "schedule", "mode": "daily"}),
        node("a", "action", {"action_type": "plugin__dice-roller__roll"}),
        node("e", "end"))),
    "morning": command(UUID + "04", "Morning", [{"type": "event", "event_name": "startup"}],
                       [{"type": "notify", "title": "Good morning"}]),
    "on-crit": command(UUID + "05", "On crit", workflow=graph(
        node("t", "trigger", {"trigger_type": "plugin__dice-roller__on_natural_20"}),
        node("a", "action", {"action_type": "speak"}),
        node("n", "sticky_note", {"text": "celebrate"}))),
    "conditional": command(UUID + "06", "Conditional", [{"type": "text", "phrases": ["maybe"]}],
                           [{"type": "condition", "if_true": [{"type": "open_url", "url": "https://example.invalid"}],
                             "if_false": [{"type": "wait", "ms": 10}]}]),
    "open-file": command(UUID + "07", "Open notes", [{"type": "text", "phrases": ["notes"]}],
                         [{"type": "execute", "shell": "open", "path": "~/notes.txt"}]),
    "event-node-startup": command(UUID + "08", "Startup node", workflow=graph(
        node("t", "trigger", {"trigger_type": "event", "config": {"event_name": "startup"}}),
        node("a", "action", {"action_type": "notify"}))),
    # hostile
    "linear-open-file": command(UUID + "25", "Linear open_file", [{"type": "text", "phrases": ["x"]}],
                                [{"type": "open_file", "path": "~/x"}]),
    "event-node-no-config": command(UUID + "26", "Event name in the wrong place", workflow=graph(
        node("t", "trigger", {"trigger_type": "event", "event_name": "startup"}),
        node("a", "action", {"action_type": "notify"}))),
    "caps-mismatch": command(UUID + "10", "Quiet shell", [{"type": "text", "phrases": ["tidy"]}],
                             [{"type": "execute", "command": "rm -rf ~/tmp"}]),
    "unknown-action": command(UUID + "11", "Unknown action", [{"type": "text", "phrases": ["go"]}],
                              [{"type": "download_and_run", "url": "https://example.invalid/x"}]),
    "unknown-node-action": command(UUID + "27", "Unknown node action", workflow=graph(
        node("t", "trigger", {"trigger_type": "text", "config": {"phrases": ["go"]}}),
        node("a", "action", {"action_type": "download_and_run"}))),
    "unknown-node": command(UUID + "12", "Unknown node", workflow=graph(
        node("s", "start"), node("x", "teleport", {"to": "elsewhere"}))),
    "unknown-trigger": command(UUID + "13", "Unknown trigger", [{"type": "geofence", "radius": 5}],
                               [{"type": "speak", "text": "hi"}]),
    "unknown-trigger-node": command(UUID + "14", "Reminder trigger", workflow=graph(
        node("t", "trigger", {"trigger_type": "reminder"}), node("a", "action", {"action_type": "speak"}))),
    "unknown-event-name": command(UUID + "15", "Unknown event", [{"type": "event", "event_name": "usb_inserted"}],
                                  [{"type": "speak", "text": "hi"}]),
    "undeclared-trigger-cap": command(UUID + "16", "Hotkey", [{"type": "hotkey", "modifiers": ["ctrl"], "key": "h"}],
                                      [{"type": "speak", "text": "hi"}]),
    "undeclared-uses-plugin": command(UUID + "17", "Plugin action", [{"type": "text", "phrases": ["roll"]}],
                                      [{"type": "dynamic", "handler_id": "plugin__dice-roller__roll"}]),
    "bare-dynamic": command(UUID + "18", "Bare dynamic", workflow=graph(
        node("t", "trigger", {"trigger_type": "text", "phrases": ["x"]}),
        node("a", "action", {"action_type": "dynamic"}))),
    "two-spellings": command(UUID + "19", "Two spellings", workflow=graph(
        node("t", "trigger", {"trigger_type": "text", "phrases": ["x"]}),
        node("a", "action", {"action_type": "speak", "action": {"type": "execute", "command": "curl x | sh"}}))),
    "danger-understated": command(UUID + "20", "Understated", [{"type": "text", "phrases": ["run"]}],
                                  [{"type": "run_command", "command_id": UUID + "01"}]),
    "unparsed-handler": command(UUID + "21", "Unparsed handler", [{"type": "text", "phrases": ["x"]}],
                                [{"type": "dynamic", "handler_id": "dice-roller"}]),
    "sub-workflow": command(UUID + "23", "Sub workflow", workflow=graph(
        node("t", "trigger", {"trigger_type": "text", "phrases": ["x"]}),
        node("w", "sub_workflow", {"workflow_id": UUID + "10"}))),
    "requires-unlisted": command(UUID + "22", "Ghost plugin", [{"type": "text", "phrases": ["boo"]}],
                                 [{"type": "dynamic", "handler_id": "plugin__ghost-plugin__haunt"}]),
}


DUPLICATE_TYPE = (
    '{\n  "id": "00000000-0000-4000-8000-000000000024",\n  "name": "Duplicate type",\n'
    '  "triggers": [{"type": "text", "phrases": ["x"]}],\n'
    '  "actions": [{"type": "speak", "type": "execute", "command": "curl x | sh", "text": "hi"}],\n'
    '  "enabled": true\n}\n')


VALID_COMMANDS = ("greet", "build-and-ask", "roll-dice", "morning", "on-crit", "conditional", "open-file",
                  "event-node-startup")


def gen_commands() -> dict[str, bytes]:
    out = {}
    # a serde tag spelled twice: which `type` an action has depends on the reader
    put("commands/hostile/duplicate-type-key.command.json", DUPLICATE_TYPE)
    for name, d in COMMANDS.items():
        b = C.pretty(d).encode("utf-8")
        sub = "valid" if name in VALID_COMMANDS else "hostile"
        put(f"commands/{sub}/{name}.command.json", b)
        out[name] = b
    return out


# ── signed documents ─────────────────────────────────────────────────────

def base_entry(eid: str, art: bytes, media: str) -> dict:
    return {"id": eid, "version": "1.0.0", "author": "test-author", "listing": LISTING, "thumbnail": THUMBNAIL,
            "artefact": {"sha256": sha(art), "size": len(art), "media_type": media},
            "review": "unchecked", "min_astra": "0.2.8", "published_at": T0 - 86400}


def command_entry(name: str, art: bytes, caps, danger, requires=()) -> dict:
    e = base_entry(name, art, "application/vnd.astra.command+json")
    cmd_part = C.part_digest({f"{name}.command.json": art}, root=None)
    e.update({
        "capabilities": sorted(caps), "danger": danger, "platforms": ["linux", "macos", "windows"],
        "requires": [{"kind": "plugin", "id": r, "version_req": ">=1.0.0"} for r in requires],
        "parts": [{"part_kind": "command", "digest": cmd_part, "size": len(art)}],
        "content_confirmed": {"command-rights-v1": 1},
        "licence": DECLARED_CC_BY, "credits": CREDITS,
    })
    return e


def index_signed(kind: str, entries: list, issued: int = T0, span: int = WEEK) -> dict:
    return {"schema": f"astra.{kind}.index/1", "serial": issued, "issued_at": issued,
            "expires_at": issued + span, "entries": entries}


def withdrawn_signed(kind: str, rows: list, lifts: list, issued: int = T0, span: int = WEEK) -> dict:
    return {"schema": f"astra.{kind}.withdrawn/1", "serial": issued, "issued_at": issued,
            "expires_at": issued + span, "rows": rows, "lifts": lifts}


def put_doc(rel: str, kind: str, doc: str, signed: dict, role: str = "current", signer: str | None = None,
            sign_domain: str | None = None) -> None:
    domain = f"astra.{kind}.{doc}/1"
    put_json(rel, envelope(domain, signed, signer or kind_key_id(kind, role), sign_domain))


def gen_index(cmds: dict[str, bytes], bundles: dict[str, bytes]) -> dict[str, dict]:
    valid: dict[str, dict] = {}
    c_entries = [
        command_entry("greet", cmds["greet"], ["on_phrase", "plays_audio", "uses_ai"], "low"),
        command_entry("build-and-ask", cmds["build-and-ask"], ["binds_hotkey", "executes_shell", "uses_ai"], "critical"),
        command_entry("roll-dice", cmds["roll-dice"], ["on_schedule", "uses_plugin:dice-roller"], "high", ["dice-roller"]),
        command_entry("morning", cmds["morning"], ["on_startup", "sends_notifications"], "low"),
        command_entry("on-crit", cmds["on-crit"], ["plays_audio", "uses_plugin:dice-roller"], "low", ["dice-roller"]),
        command_entry("conditional", cmds["conditional"], ["on_phrase", "opens_urls"], "high"),
    ]
    # display-only, never compared (design §11a.9): a detail that disagrees with `commercial` is still valid
    c_entries[0]["licence"] = dict(DECLARED_CC_BY, commercial_detail="Disallow")
    valid["commands"] = index_signed("commands", c_entries)

    model = base_entry("aiko-body", bundles["model"], "application/vnd.astra.character+zip")
    model.update({"format": "astra.character", "body_kind": "vrm",
                  "parts": [{"part_kind": "character", "digest": MODEL_PART, "size": len(BODY)}],
                  "content_confirmed": {"character-rights-v1": 1}, "licence": VRM1_LICENCE, "credits": CREDITS})
    valid["models"] = index_signed("models", [model])

    anim = base_entry("wave-set", bundles["animset"], "application/vnd.astra.animpack+zip")
    anim.update({"format": "astra.animpack", "dimension": "3d",
                 "parts": [{"part_kind": "animations", "digest": ANIMSET_PART,
                            "size": sum(len(x) for x in ASCII_PART.values())}],
                 "clips": 2, "states": ["idle", "wave"], "content_confirmed": {"animations-rights-v1": 1},
                 "licence": DECLARED_CC_BY, "credits": CREDITS})
    valid["animsets"] = index_signed("animsets", [anim])

    char = base_entry("aiko", bundles["character"], "application/vnd.astra.character+zip")
    char.update({"format": "astra.character",
                 "requires": [{"kind": "model", "id": "aiko-body", "version": "1.0.0", "digest": MODEL_PART},
                              {"kind": "animset", "id": "wave-set", "version": "1.0.0", "digest": ANIMSET_PART}],
                 "parts": [], "content_confirmed": {}, "needs": [], "licence": DECLARED_CC_BY, "credits": CREDITS})
    valid["characters"] = index_signed("characters", [char])

    pack = {"id": "aiko-starter", "version": "1.0.0", "author": "test-author", "listing": LISTING,
            "thumbnail": THUMBNAIL, "review": "unchecked", "published_at": T0 - 86400,
            "members": [{"kind": "model", "id": "aiko-body", "version": "1.0.0", "digest": sha(bundles["model"])},
                        {"kind": "animset", "id": "wave-set", "version": "1.0.0", "digest": sha(bundles["animset"])},
                        {"kind": "command", "id": "greet", "version": "1.0.0", "digest": sha(cmds["greet"])}]}
    valid["packs"] = index_signed("packs", [pack])

    for k in KINDS:
        put_doc(f"index/{k}/valid.json", k, "index", valid[k])

    # signatures and scoping (trust-kind-keys-v1.md §5)
    v = valid["commands"]
    put_doc("index/commands/signed-by-next.json", "commands", "index", v, role="next")
    # issued while only `current` is valid, and signed by `next`: refused until next's not_before
    put_doc("index/commands/next-before-not-before.json", "commands", "index",
            index_signed("commands", copy.deepcopy(c_entries), issued=NOV15 - 3600), role="next")
    # dual-signed during a switch, in both orders (F9): either order must retire `current`
    a, b = kind_key_id("commands", "current"), kind_key_id("commands", "next")
    put_json("index/commands/dual-signed-current-first.json", envelope("astra.commands.index/1", v, [a, b]))
    put_json("index/commands/dual-signed-next-first.json", envelope("astra.commands.index/1", v, [b, a]))
    put_doc("index/commands/signed-by-models-key.json", "commands", "index", v, signer=kind_key_id("models", "current"))
    put_doc("index/commands/signed-by-index-key.json", "commands", "index", v, signer=INDEX_KEY)
    put_doc("index/commands/signed-under-models-domain.json", "commands", "index", v,
            sign_domain="astra.models.index/1")
    # a duplicate member name: a last-wins verifier sees `critical` and verifies; a first-wins
    # reader of the same bytes sees `low` (common-v1.md §1). Refused as malformed, never verified
    text = C.pretty(envelope("astra.commands.index/1", v, kind_key_id("commands", "current")))
    needle = '"danger": "critical"'
    assert text.count(needle) == 1
    put("index/commands/duplicate-member-name.json", text.replace(needle, '"danger": "low",\n      ' + needle))
    tampered = envelope("astra.commands.index/1", v, kind_key_id("commands", "current"))
    tampered["signed"] = copy.deepcopy(v)
    tampered["signed"]["entries"][1]["capabilities"] = ["binds_hotkey", "uses_ai"]  # executes_shell hidden after signing
    put_json("index/commands/tampered-after-signing.json", tampered)

    # one defect each, re-signed so the defect is the only thing wrong
    def bad(kind: str, name: str, mutate) -> None:
        s = copy.deepcopy(valid[kind])
        mutate(s)
        put_doc(f"index/{kind}/{name}.json", kind, "index", s)

    def e0(s):
        return s["entries"][0]

    # the shared rights-text ids are dotted (`market.rights.animations`, the games pattern)
    dotted = copy.deepcopy(valid["commands"])
    dotted["entries"][0]["content_confirmed"] = {"market.rights.animations": 2}
    put_doc("index/commands/content-confirmed-dotted-id.json", "commands", "index", dotted)
    bad("commands", "content-confirmed-malformed-id", lambda s: e0(s).update(content_confirmed={"market..rights": 1}))
    bad("commands", "expiry-span-too-long", lambda s: s.update(expires_at=s["issued_at"] + 8 * 86400 + 1))
    bad("commands", "issued-in-future", lambda s: s.update(issued_at=T0 + 86400 + 1, serial=T0 + 86400 + 1,
                                                         expires_at=T0 + 86400 + 1 + WEEK))
    bad("commands", "serial-not-issued-at", lambda s: s.update(serial=s["issued_at"] - 1))
    bad("commands", "licence-prohibited", lambda s: e0(s)["licence"].update(redistribution="prohibited"))
    bad("commands", "no-command-part", lambda s: e0(s).update(parts=[dict(e0(s)["parts"][0], part_kind="art")]))
    bad("commands", "capabilities-unsorted", lambda s: e0(s).update(capabilities=["uses_ai", "on_phrase", "plays_audio"]))
    bad("commands", "unknown-top-level-key", lambda s: s.update(withdrawn=[]))
    bad("commands", "requires-kind-model", lambda s: e0(s).update(requires=[{"kind": "model", "id": "aiko-body", "version_req": "1.0.0"}]))
    bad("commands", "id-double-hyphen", lambda s: e0(s).update(id="gr--eet"))
    bad("commands", "parts-without-confirmation", lambda s: e0(s).update(content_confirmed={}))
    bad("commands", "duplicate-id-version", lambda s: s["entries"].append(copy.deepcopy(e0(s))))
    bad("commands", "danger-unknown-word", lambda s: e0(s).update(danger="medium"))
    bad("characters", "requires-no-model", lambda s: e0(s).update(requires=[r for r in e0(s)["requires"] if r["kind"] != "model"]))
    bad("characters", "requires-two-models", lambda s: e0(s)["requires"].append(
        {"kind": "model", "id": "other-body", "version": "1.0.0", "digest": MODEL_PART}))
    bad("characters", "part-kind-animations", lambda s: e0(s).update(parts=[{"part_kind": "animations", "digest": ANIMSET_PART, "size": 1}]))
    bad("models", "two-parts", lambda s: e0(s)["parts"].append(dict(e0(s)["parts"][0], part_kind="character")))
    bad("models", "format-vrm-body-pixel", lambda s: e0(s).update(format="vrm", body_kind="pixel"))
    bad("models", "licence-vrm-spec-none", lambda s: e0(s)["licence"].update(spec="none"))
    bad("models", "avatar-author-only", lambda s: e0(s)["licence"].update(avatar_permission="author_only"))
    bad("models", "vrm0-political-known", lambda s: e0(s)["licence"].update(
        spec="vrm0", commercial_detail="Allow", usage=dict(VRM1_LICENCE["usage"])))
    bad("animsets", "dimension-2d-animations-part", lambda s: e0(s).update(dimension="2d"))
    bad("animsets", "clips-zero", lambda s: e0(s).update(clips=0))
    bad("packs", "member-pack", lambda s: e0(s)["members"].append({"kind": "pack", "id": "x", "version": "1.0.0", "digest": MODEL_PART}))
    bad("packs", "min-astra-present", lambda s: e0(s).update(min_astra="0.2.8"))
    bad("packs", "licence-present", lambda s: e0(s).update(licence=DECLARED_CC_BY))
    bad("packs", "members-65", lambda s: e0(s).update(members=[
        {"kind": "command", "id": f"c{i:02d}", "version": "1.0.0", "digest": MODEL_PART} for i in range(65)]))
    # schema- and rule-valid, but the model digest it pins is not the served model's part digest: the
    # CLIENT must refuse it on its own (requires-digest-mismatch, design §11a.10), whatever ingest did
    bad("characters", "requires-stale-digest", lambda s: e0(s)["requires"][0].update(digest=sha(b"stale")))
    bad("packs", "duplicate-member", lambda s: e0(s)["members"].append(copy.deepcopy(e0(s)["members"][0])))
    return valid


def row(rid, act, floor, reason, at, versions="<=1.0.0", **kw) -> dict:
    r = {"id": rid, "versions": versions, "act": act, "floor_effect": floor, "reason_code": reason,
         "reason_text": f"test row: {act}/{reason}", "at": at}
    r.update(kw)
    return r


def gen_withdrawn(cmds: dict[str, bytes], bundles: dict[str, bytes]) -> None:
    cmd_part = C.part_digest({"greet.command.json": cmds["greet"]}, root=None)
    lift_old = {"id": "old-shell", "versions": "<=0.9.0", "lifts_at": T0 - 40 * 86400}
    valid = {
        "commands": withdrawn_signed("commands", [
            row("evil-shell", "security", "disarm", "security", T0 - 3600),
            row("greet-copy", "rights", "disarm", "rights-holder", T0 - 7200,
                part={"part_kind": "command", "digest": cmd_part}),
            row("needs-ghost", "retired", "no-update", "requires-unavailable", T0 - 600,
                cause={"kind": "plugin", "id": "ghost-plugin", "version": "1.0.0"}),
        ], [lift_old]),
        "characters": withdrawn_signed("characters", [
            row("mika", "retired", "no-update", "member-withdrawn", T0 - 600,
                cause={"kind": "model", "id": "stolen-body", "version": "1.0.0"}),
        ], []),
        "models": withdrawn_signed("models", [row("stolen-body", "rights", "disarm", "rights-holder", T0 - 900,
                                                  part={"part_kind": "character", "digest": MODEL_PART})], []),
        "animsets": withdrawn_signed("animsets", [row("old-dance", "retired", "no-update", "author-request", T0 - 50)], []),
        "packs": withdrawn_signed("packs", [
            row("aiko-starter", "security", "disarm", "member-withdrawn", T0 - 300,
                cause={"kind": "model", "id": "aiko-body", "version": "1.0.0"}),
        ], []),
    }
    for k in KINDS:
        put_doc(f"withdrawn/{k}/valid.json", k, "withdrawn", valid[k])

    # the served state a pack/character ingest is judged against (scenarios)
    put_doc("withdrawn/models/aiko-security.json", "models", "withdrawn", withdrawn_signed("models", [
        row("aiko-body", "security", "disarm", "security", T0 - 400)], []))
    put_doc("withdrawn/packs/no-cascade.json", "packs", "withdrawn", withdrawn_signed("packs", [], []))
    put_doc("withdrawn/characters/no-cascade.json", "characters", "withdrawn", withdrawn_signed("characters", [], []))
    put_doc("withdrawn/characters/aiko-cascade.json", "characters", "withdrawn", withdrawn_signed("characters", [
        row("aiko", "security", "disarm", "member-withdrawn", T0 - 300,
            cause={"kind": "model", "id": "aiko-body", "version": "1.0.0"})], []))

    # the sticky-security sequence (trust-kind-keys-v1.md §7.2)
    sec = row("evil-shell", "security", "disarm", "security", T0 - 3600)
    put_doc("withdrawn/commands/seq-1-security.json", "commands", "withdrawn",
            withdrawn_signed("commands", [sec], [], issued=T0))
    put_doc("withdrawn/commands/seq-2-row-dropped.json", "commands", "withdrawn",
            withdrawn_signed("commands", [], [], issued=T0 + 3600))
    put_doc("withdrawn/commands/seq-3-lift-wrong-at.json", "commands", "withdrawn",
            withdrawn_signed("commands", [], [{"id": "evil-shell", "versions": "<=1.0.0", "lifts_at": T0 - 3599}],
                             issued=T0 + 7200))
    put_doc("withdrawn/commands/seq-4-lift.json", "commands", "withdrawn",
            withdrawn_signed("commands", [], [{"id": "evil-shell", "versions": "<=1.0.0", "lifts_at": T0 - 3600}],
                             issued=T0 + 10800))

    # every row is sticky (F14): a cascade `retired` row, dropped, re-asserted beside its lift, lifted
    # under a near-miss spelling, and finally lifted exactly, with the cause the cascade named
    cause = {"kind": "plugin", "id": "ghost-plugin", "version": "1.0.0"}
    ret = row("needs-ghost", "retired", "no-update", "requires-unavailable", T0 - 600, cause=cause)
    exact = {"id": "needs-ghost", "versions": "<=1.0.0", "lifts_at": T0 - 600, "cause": cause}
    for n, (rows, lifts) in enumerate([([ret], []), ([], []), ([ret], [exact]),
                                       ([], [dict(exact, versions="<= 1.0.0")]), ([], [exact])], 1):
        put_doc(f"withdrawn/commands/seqr-{n}.json", "commands", "withdrawn",
                withdrawn_signed("commands", rows, lifts, issued=T0 + n * 3600))

    def bad(kind: str, name: str, mutate) -> None:
        s = copy.deepcopy(valid[kind])
        mutate(s)
        put_doc(f"withdrawn/{kind}/{name}.json", kind, "withdrawn", s)

    def r0(s):
        return s["rows"][0]

    bad("commands", "security-reason-retired-act", lambda s: r0(s).update(act="retired", floor_effect="no-update"))
    bad("commands", "security-floor-not-disarm", lambda s: r0(s).update(floor_effect="no-update"))
    bad("commands", "rights-floor-no-offer", lambda s: s["rows"][1].update(floor_effect="no-offer"))
    bad("commands", "retired-floor-no-offer", lambda s: s["rows"][2].update(floor_effect="no-offer"))
    bad("commands", "part-without-rights", lambda s: r0(s).update(part={"part_kind": "command", "digest": cmd_part}))
    bad("commands", "cascade-without-cause", lambda s: s["rows"][2].pop("cause"))
    bad("commands", "lift-contradicts-row", lambda s: s["lifts"].append(
        {"id": "evil-shell", "versions": "<=1.0.0", "lifts_at": T0 - 3600}))
    bad("commands", "lift-contradicts-retired-row", lambda s: s["lifts"].append(
        {"id": "needs-ghost", "versions": "<=1.0.0", "lifts_at": T0 - 600, "cause": s["rows"][2]["cause"]}))
    bad("commands", "range-with-space", lambda s: r0(s).update(versions="<= 1.0.0"))
    bad("commands", "range-upper-first", lambda s: r0(s).update(versions="<=1.0.0,>=0.5.0"))
    bad("commands", "bad-act-enum", lambda s: r0(s).update(act="quarantine"))
    bad("commands", "missing-lifts", lambda s: s.pop("lifts"))
    bad("packs", "row-with-part", lambda s: r0(s).update(part={"part_kind": "character", "digest": MODEL_PART}))
    bad("models", "expiry-span-too-long", lambda s: s.update(expires_at=s["issued_at"] + 9 * 86400))


# ── trust: the kind_keys member (trust-kind-keys-v1.md) ──────────────────

def gen_trust() -> None:
    rows = kind_keys_rows()
    signed = {"schema": "astra.registry.trust/1", "serial": 7, "issued_at": "2026-11-01T00:00:00Z",
              "expires_at": "2027-02-01T00:00:00Z", "index_keys": index_keys_rows(),
              "reusable_workflow_shas": [], "kind_keys": rows}
    put_json("trust/trust.json", envelope("astra.registry.trust/1", signed, ROOT_KEY,
                                          comment="TEST trust.json: every key in it is a published TEST key"))

    def variant(name: str, mutate) -> None:
        r = copy.deepcopy(rows)
        ik = index_keys_rows()
        mutate(r, ik)
        put_json(f"trust/kind-keys/{name}.json", {"index_keys": ik, "kind_keys": r})

    def find(r, kind, role):
        return next(x for x in r if x["kind"] == kind and x["role"] == role)

    variant("valid", lambda r, ik: None)
    variant("next-not-later", lambda r, ik: find(r, "commands", "next").update(not_before=CURRENT_NB))
    variant("next-earlier", lambda r, ik: find(r, "characters", "next").update(not_before="2026-09-01T00:00:00Z"))
    variant("duplicate-role", lambda r, ik: find(r, "models", "next").update(role="current"))
    variant("bad-alg", lambda r, ik: find(r, "animsets", "current").update(alg="ed448"))
    variant("bad-role", lambda r, ik: find(r, "packs", "next").update(role="spare"))
    variant("missing-next", lambda r, ik: r.remove(find(r, "games", "next")))
    variant("shared-key-across-kinds", lambda r, ik: find(r, "models", "current").update(
        public_key=find(r, "commands", "current")["public_key"]))
    variant("kind-key-in-index-keys", lambda r, ik: ik.append(
        {"key_id": "astra-index-2026z", "public_key": find(r, "commands", "current")["public_key"],
         "not_before": "2026-07-01T00:00:00Z", "not_after": "2027-07-01T00:00:00Z", "comment": "TEST"}))
    variant("unknown-kind-row", lambda r, ik: r.append(
        {"kind": "emotes", "role": "current", "key_id": "astra-emotes-2026a", "alg": "ed25519",
         "public_key": key("astra-emotes-2026a")[1], "not_before": CURRENT_NB}))
    variant("bad-public-key", lambda r, ik: find(r, "commands", "next").update(public_key="AAAA"))
    variant("unparseable-not-before", lambda r, ik: find(r, "animsets", "next").update(not_before="next week"))


# ── archives: the hostile set (ingest-v1.md §3, design §10 guard list) ───

def gen_archives() -> None:
    model_files = dict(MODEL_FILES)

    def hostile(name: str, data: bytes) -> None:
        put(f"archives/hostile/{name}", data)

    good = bundle("astra.character", model_files, body=BODY_PATH)
    # a decoy end record after the real one: it ends the file exactly, counts ONE entry, and points
    # at a directory that does not end where it begins (end_record.rs, review 2026-10-27)
    cd_start = good.rfind(b"PK\x01\x02", 0, good.rfind(b"PK\x05\x06"))
    real_cd = good.find(b"PK\x01\x02")
    decoy = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, 1, 1, 46 + len(BODY_PATH), real_cd, 0)
    hostile("decoy-end-record.astrachar", good + decoy)
    assert cd_start >= real_cd
    hostile("trailing-junk.astrachar", good + b"\x00" * 64)
    # 10,001 real entries, each name unique (base-36, three characters) so nothing but the count is wrong
    many = {}
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    for i in range(10001):
        n = digits[i // 1296] + digits[(i // 36) % 36] + digits[i % 36]
        many[f"x/{n}"] = b""
    hostile("entries-10001.astrachar", zip_bytes(
        [{"name": p, "data": b, "method": 0} for p, b in many.items()] +
        [{"name": "astrachar.json", "data": b"{}", "method": 0}]))

    def renamed(old: str, new: str, local_too: bool = True):
        def t(entries):
            for e in entries:
                if e["name"] == old:
                    e["name"] = new
                    if local_too:
                        e["local_name"] = new
            return entries
        return t

    hostile("name-dotdot.astrachar", bundle("astra.character", model_files, BODY_PATH,
                                            tweak=renamed(BODY_PATH, "characters/../../body.vrm")))
    hostile("name-not-nfc.astrachar", bundle("astra.character", model_files, BODY_PATH,
                                             tweak=renamed(BODY_PATH, "characters/aiko/bódy.vrm")))
    hostile("name-case-collision.astrachar", bundle(
        "astra.character", {BODY_PATH: BODY, "characters/aiko/BODY.vrm": BODY}, BODY_PATH))
    hostile("name-control-character.astrachar", bundle("astra.character", model_files, BODY_PATH,
                                                       tweak=renamed(BODY_PATH, "characters/aiko/bo\u0085dy.vrm")))

    def attr(path: str, **kw):
        def t(entries):
            for e in entries:
                if e["name"] == path:
                    e.update(kw)
            return entries
        return t

    link = {**model_files, "characters/aiko/notes.txt": b"../../../../etc/passwd"}
    hostile("symlink-entry.astrachar", bundle("astra.character", link, BODY_PATH,
                                              tweak=attr("characters/aiko/notes.txt", ext_attr=0o120777 << 16)))
    # zip 9.2.0 `get_unix_mode` reads the unix mode for ANY non-DOS host: a link is a link on host 19 or 10 too
    # (inside an animset part, so the link rule is the ONLY thing between the file and publication)
    linked = {**ASCII_PART, "clips/c.fbx": b"../../../../etc/passwd"}
    for host in (19, 10):
        put(f"archives/hostile/symlink-host-{host}.astrapack", bundle("astra.animpack", linked, body=None, tweak=attr(
            "clips/c.fbx", ext_attr=0o120777 << 16, made_by=(host << 8) | 20)))
    hostile("encrypted-entry.astrachar", bundle("astra.character", model_files, BODY_PATH,
                                                tweak=attr(BODY_PATH, flags=1)))
    bomb = {**model_files, "characters/aiko/zeros.bin": b"\x00" * (1024 * 1024)}
    hostile("ratio-bomb.astrachar", bundle("astra.character", bomb, BODY_PATH))
    hostile("deflated-vrm.astrachar", bundle("astra.character", model_files, BODY_PATH, methods={BODY_PATH: 8}))
    hostile("header-name-differs.astrachar", bundle("astra.character", model_files, BODY_PATH,
                                                    tweak=attr(BODY_PATH, local_name="characters/aiko/other.vrm")))
    upath = struct.pack("<HHB", 0x7075, 5 + len("x.vrm"), 1) + struct.pack("<I", zlib.crc32(BODY_PATH.encode())) + b"x.vrm"
    # the crate refuses 0x7075 in the local header too (read/mod.rs:446): one there and only there
    clip = "clips/a.fbx"
    up_local = struct.pack("<HHB", 0x7075, 5 + len("x.fbx"), 1) + struct.pack("<I", zlib.crc32(clip.encode())) + b"x.fbx"
    put("archives/hostile/upath-local-only.astrapack", bundle("astra.animpack", ASCII_PART, body=None,
                                                             tweak=attr(clip, local_extra=up_local)))
    hostile("upath-extra.astrachar", bundle("astra.character", model_files, BODY_PATH, tweak=attr(BODY_PATH, extra=upath)))
    def pad(path: str, junk: bytes):
        return attr(path, pad_before=junk)

    hostile("gap-between-entries.astrachar", bundle("astra.character", model_files, BODY_PATH,
                                                    tweak=pad("astrachar.json", b"PK\x03\x04HIDDEN-ENTRY")))
    hostile("overlapping-entries.astrachar", bundle(
        "astra.character", model_files, BODY_PATH, tweak=lambda es: es[:1] + [{"alias_of": 0}] + es[1:]))
    # three directory entries, an end record counting two: the third (a second name for the body's
    # bytes) is seen only by a reader that walks the directory rather than trusting the count
    hostile("count-short-of-directory.astrachar", zip_bytes(
        bundle_entries("astra.character", model_files, BODY_PATH) + [{"alias_of": 0, "name": "characters/aiko/hidden.vrm"}],
        eocd_override=lambda n, size, off: (n - 1, n - 1, size, off)))
    # bit 3 (ingest-v1.md §3 step 3): the descriptor is parsed and must equal the central record
    def dd(**kw):
        return attr("astrachar.json", dd=kw)
    put("archives/valid/model-aiko-descriptor.astrachar",
        bundle("astra.character", model_files, BODY_PATH, tweak=dd(sig=True)))
    put("archives/valid/model-aiko-descriptor-nosig.astrachar",
        bundle("astra.character", model_files, BODY_PATH, tweak=dd(sig=False)))
    hostile("descriptor-crc-differs.astrachar", bundle("astra.character", model_files, BODY_PATH,
                                                       tweak=dd(sig=True, crc=0x12345678)))
    hostile("stored-bit3.astrachar", bundle("astra.character", model_files, BODY_PATH,
                                            tweak=attr(BODY_PATH, dd={"sig": True})))
    hostile("bit3-local-only.astrachar", bundle("astra.character", model_files, BODY_PATH,
                                                tweak=dd(sig=True, central_bit3=False, local_sizes=True)))
    # the manifest's LOCAL header is first in the file while the directory lists it last: "last"
    # must mean last by position too, so directory order must be file order (§3 steps 3, 8)
    first = bundle_entries("astra.character", model_files, BODY_PATH, manifest_last=False)
    hostile("manifest-first-by-offset.astrachar", zip_bytes(first, cd_order=list(range(1, len(first))) + [0]))
    # zip64, in each of its spellings, is not accepted in v1 (OPEN.md O-7; §3 step 1)
    def patch_cd(b: bytes, name: str, field: int, value: int) -> bytes:
        q = b.find(b"PK\x01\x02")
        while q >= 0:
            nl = struct.unpack("<H", b[q + 28:q + 30])[0]
            if b[q + 46:q + 46 + nl] == name.encode():
                return b[:q + field] + struct.pack("<I", value) + b[q + field + 4:]
            q = b.find(b"PK\x01\x02", q + 4)
        raise KeyError(name)
    z64 = struct.pack("<HHQQ", 0x0001, 16, len(BODY), len(BODY))
    hostile("zip64-extra.astrachar", bundle("astra.character", model_files, BODY_PATH, tweak=attr(BODY_PATH, extra=z64)))
    hostile("zip64-size-sentinel.astrachar", patch_cd(good, BODY_PATH, 20, 0xFFFFFFFF))
    hostile("zip64-offset-sentinel.astrachar", patch_cd(good, BODY_PATH, 42, 0xFFFFFFFF))
    hostile("zip64-cd-size-sentinel.astrachar", zip_bytes(
        bundle_entries("astra.character", model_files, BODY_PATH),
        eocd_override=lambda n, size, off: (n, n, 0xFFFFFFFF, off)))
    hostile("method-bzip2.astrachar", bundle("astra.character", {**model_files, "characters/aiko/notes.ogg": b"OggS-bz"},
                                             BODY_PATH, tweak=attr("characters/aiko/notes.ogg", method=12)))
    hostile("directory-with-data.astrachar", bundle(
        "astra.character", model_files, BODY_PATH,
        tweak=lambda es: [{"name": "characters/aiko/dir/", "data": b"hidden", "method": 0}] + es))

    def dup_manifest(es):
        for e in es:
            if e["name"] == "astrachar.json":
                e["data"] = e["data"].replace(b'"format": ', b'"format": "astra.animpack",\n "format": ', 1)
        return es
    hostile("manifest-duplicate-key.astrachar", bundle("astra.character", model_files, BODY_PATH, tweak=dup_manifest))
    hostile("manifest-not-last.astrachar", bundle("astra.character", model_files, BODY_PATH, manifest_last=False))
    hostile("file-unlisted.astrachar", bundle("astra.character", {**model_files, "characters/aiko/extra.txt": b"x"},
                                              BODY_PATH, listed=model_files))
    hostile("file-digest-wrong.astrachar", bundle("astra.character", model_files, BODY_PATH,
                                                  listed={BODY_PATH: BODY + b"!"}))

    # the VRM licence verdict on EVERY .vrm and .glb (ingest-v1.md §4; PR #120's rule)
    hat = vrm1(dict(VRM1_ALLOWED, avatarPermission="onlyAuthor"))
    hostile("glb-prohibited-beside-allowed-body.astrachar", bundle(
        "astra.character", {**model_files, "characters/aiko/accessories/hat/hat.glb": hat}, BODY_PATH))
    # the verdict follows CONTENT, not names (F2): a GLB is judged by its magic, a .gltf as JSON
    hostile("body-renamed-bin.astrachar", bundle("astra.character", {"characters/aiko/body.bin": BODY},
                                                 "characters/aiko/body.bin"))
    hostile("accessory-glb-renamed.astrachar", bundle(
        "astra.character", {**model_files, "characters/aiko/accessories/hat/hat.dat": hat}, BODY_PATH))
    hat_gltf = json.dumps({"asset": {"version": "2.0"}, "extensions": {"VRMC_vrm": {
        "specVersion": "1.0", "meta": dict(VRM1_ALLOWED, avatarPermission="onlyAuthor")}},
        "extensionsUsed": ["VRMC_vrm"]}, sort_keys=True).encode()
    hostile("gltf-prohibited.astrachar", bundle(
        "astra.character", {**model_files, "characters/aiko/accessories/hat/hat.gltf": hat_gltf}, BODY_PATH))
    hostile("file-outside-parts.astrachar", bundle(
        "astra.character", {**model_files, "characters/aiko/payload.bin": b"\x7fELF-not-a-part"}, BODY_PATH))
    hostile("vrm-redistribution-prohibited.astrachar", bundle(
        "astra.character", {BODY_PATH: vrm1(dict(VRM1_ALLOWED, allowRedistribution=False))}, BODY_PATH))
    absent = dict(VRM1_ALLOWED)
    del absent["allowRedistribution"]
    hostile("vrm-field-absent.astrachar", bundle("astra.character", {BODY_PATH: vrm1(absent)}, BODY_PATH))
    hostile("vrm-named-people.astrachar", bundle(
        "astra.character", {BODY_PATH: vrm1(dict(VRM1_ALLOWED, avatarPermission="onlySeparatelyLicensedPerson"))},
        BODY_PATH))
    # the glTF JSON names allowRedistribution twice: last-wins reads true, first-wins reads false
    dup = vrm1(dict(VRM1_ALLOWED, allowRedistribution=False))
    dup_json = dup[20:].replace(b'"allowRedistribution":false', b'"allowRedistribution":false,"allowRedistribution":true', 1)
    dup_json = dup_json.rstrip(b" ")
    dup_json += b" " * (-len(dup_json) % 4)
    dup = struct.pack("<4sII", b"glTF", 2, 20 + len(dup_json)) + struct.pack("<I4s", len(dup_json), b"JSON") + dup_json
    hostile("vrm-duplicate-key.astrachar", bundle("astra.character", {BODY_PATH: dup}, BODY_PATH))
    # the same duplicate-key GLB as a character ACCESSORY (not the body) and as a clip in an ANIMSET
    hostile("accessory-duplicate-key.astrachar", bundle(
        "astra.character", {**CHAR_FILES, "characters/aiko/accessories/hat/hat.glb": dup}, None))
    put("archives/hostile/animset-glb-duplicate-key.astrapack", bundle(
        "astra.animpack", {**ASCII_PART, "clips/hat.glb": dup}, body=None))
    # unrecognised licence tokens are UNKNOWN, never Allowed (meta.rs at 045b0bf; F3)
    def vrm0(meta: dict) -> bytes:
        return glb({"asset": {"version": "2.0"}, "extensions": {"VRM": {"meta": meta}}, "extensionsUsed": ["VRM"]})
    hostile("vrm0-licence-other.astrachar", bundle(
        "astra.character", {BODY_PATH: vrm0(dict(VRM0_ALLOWED, licenseName="Other"))}, BODY_PATH))
    hostile("vrm0-user-unrecognised.astrachar", bundle(
        "astra.character", {BODY_PATH: vrm0(dict(VRM0_ALLOWED, allowedUserName="Friends"))}, BODY_PATH))
    hostile("vrm1-avatar-unrecognised.astrachar", bundle(
        "astra.character", {BODY_PATH: vrm1(dict(VRM1_ALLOWED, avatarPermission="everyoneButCompetitors"))}, BODY_PATH))
    hostile("vrm1-redistribution-string.astrachar", bundle(
        "astra.character", {BODY_PATH: vrm1(dict(VRM1_ALLOWED, allowRedistribution="true"))}, BODY_PATH))
    put("archives/valid/model-vrm0-cc-by-nc.astrachar", bundle(
        "astra.character", {BODY_PATH: vrm0(dict(VRM0_ALLOWED, licenseName="CC_BY_NC"))}, BODY_PATH))
    # a GLB is classified by its extensions, not its name (coordinator, 2026-11-01)
    vrma = glb({"asset": {"version": "2.0"}, "extensions": {"VRMC_vrm_animation": {"specVersion": "1.0"}},
                "extensionsUsed": ["VRMC_vrm_animation"]})
    dance = {"animpack.toml": b'name = "dance"\n', "clips/dance.vrma": vrma}
    put("archives/valid/animset-vrma.astrapack", bundle("astra.animpack", dance, body=None))
    avatar_vrma = glb({"asset": {"version": "2.0"}, "extensions": {
        "VRMC_vrm_animation": {"specVersion": "1.0"},
        "VRMC_vrm": {"specVersion": "1.0", "meta": dict(VRM1_ALLOWED, avatarPermission="onlyAuthor")}},
        "extensionsUsed": ["VRMC_vrm_animation", "VRMC_vrm"]})
    put("archives/hostile/vrma-avatar-prohibited.astrapack", bundle(
        "astra.animpack", {**dance, "clips/dance.vrma": avatar_vrma}, body=None))
    # a PLAIN GLB (no avatar extension, no VRMC_vrm_animation) is judged only in a character or
    # model part: a clip in an animset takes the part's rights confirmation; an accessory is held
    plain = glb({"asset": {"version": "2.0"}})
    put("archives/valid/animset-plain-glb.astrapack", bundle(
        "astra.animpack", {"animpack.toml": b'name = "glbset"\n',
                           "clips/wave.glb": plain}, body=None))
    hostile("character-plain-glb-accessory.astrachar", bundle(
        "astra.character", {**CHAR_FILES, "characters/aiko/accessories/hat/hat.glb": plain}, None))
    hostile("vrm-metas-disagree.astrachar", bundle(
        "astra.character", {BODY_PATH: vrm_both(VRM0_ALLOWED, dict(VRM1_ALLOWED, allowRedistribution=False))},
        BODY_PATH))
    # the VRM extension is there (so the body IS a VRM, ingest-v1.md §3 step 9) but carries no meta: Unknown, held
    no_meta = glb({"asset": {"version": "2.0"}, "extensions": {"VRMC_vrm": {"specVersion": "1.0"}},
                   "extensionsUsed": ["VRMC_vrm"]})
    hostile("vrm-no-meta.astrachar", bundle("astra.character", {BODY_PATH: no_meta}, BODY_PATH))
    # a GLB with no VRM extension at all is not a VRM body: a format refusal, before any licence verdict
    # the JSON chunk declares 4 KiB more than the file holds; a reader that slices to EOF reads the
    # complete (allowed) JSON anyway. A short or truncated chunk is not a GLB (ingest-v1.md §3 step 10)
    short = BODY[:12] + struct.pack("<I", int.from_bytes(BODY[12:16], "little") + 4096) + BODY[16:]
    hostile("vrm-chunk-past-eof.astrachar", bundle("astra.character", {BODY_PATH: short}, BODY_PATH))
    hostile("vrm-not-glb.astrachar", bundle("astra.character", {BODY_PATH: b"not a glb at all"}, BODY_PATH))
    hostile("vrm-no-extension.astrachar", bundle("astra.character", {BODY_PATH: vrm1(None)}, BODY_PATH))
    # the allowed body under a NEW name: the blocklist is per file sha256, so a rename does not evade it
    hostile("blocked-file-renamed.astrachar", bundle(
        "astra.character", {"characters/aiko/renamed.vrm": BODY}, "characters/aiko/renamed.vrm"))
    # the settings exemption is ONE file at ONE path, parsed as TOML (ingest-v1.md §5)
    mp3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x64" + b"\x00" * 64
    hostile("settings-mp3-bytes.astrachar", bundle("astra.character", {"characters/aiko/character.toml": mp3}, None))
    hostile("settings-second-toml.astrachar", bundle(
        "astra.character", {**CHAR_FILES, "characters/aiko/song.toml": b'title = "not settings"\n'}, None))
    # R7 (inside an animset part, where a plain glTF is never judged, so only these rules stand guard)
    def anim(extra: dict) -> bytes:
        return bundle("astra.animpack", {**ASCII_PART, **extra}, body=None)
    remote = glb({"asset": {"version": "2.0"}, "images": [{"uri": "https://example.invalid/x.png"}]})
    put("archives/hostile/glb-remote-uri.astrapack", anim({"clips/r.glb": remote}))
    escape = json.dumps({"asset": {"version": "2.0"}, "buffers": [{"uri": "../../etc/passwd", "byteLength": 4}]},
                        sort_keys=True).encode()
    put("archives/hostile/gltf-uri-escape.astrapack", anim({"clips/e.gltf": escape}))
    inside = json.dumps({"asset": {"version": "2.0"}, "buffers": [{"uri": "m.bin", "byteLength": 4}]}, sort_keys=True).encode()
    put("archives/valid/animset-gltf-relative-uri.astrapack",
        anim({"clips/m.gltf": inside, "clips/m.bin": b"\x00\x01\x02\x03"}))
    put("archives/hostile/name-device-superscript.astrapack", anim({"clips/com\u00b9.fbx": b"FBX-X"}))
    put("archives/hostile/name-device-conin.astrapack", anim({"clips/CONIN$.fbx": b"FBX-X"}))
    put("archives/hostile/file-and-directory.astrapack", anim({"clips/a.fbx/b.fbx": b"FBX-X"}))
    # S5: a text glTF under a name that is not .gltf (name and content must agree, as for the GLB magic)
    avatar_json = json.dumps({"asset": {"version": "2.0"}, "extensions": {"VRMC_vrm": {
        "specVersion": "1.0", "meta": dict(VRM1_ALLOWED, allowRedistribution=False)}},
        "extensionsUsed": ["VRMC_vrm"]}, sort_keys=True).encode()
    put("archives/hostile/gltf-named-json-in-animset.astrapack", anim({"clips/avatar.json": avatar_json}))
    hostile("gltf-named-json-accessory.astrachar", bundle(
        "astra.character", {**CHAR_FILES, "characters/aiko/accessories/x/model.json": avatar_json}, None))
    # unreadable is refused, never "plain" (an animset part never judges a plain glTF)
    put("archives/hostile/glb-invalid-json.astrapack", anim({"clips/bad.glb": _glb_of(b'{"asset": {"version": ')}))
    put("archives/hostile/gltf-invalid-json.astrapack", anim({"clips/bad.gltf": b'{"asset": {"version": "2.0"}, '}))

    def nested(depth: int) -> bytes:  # the top-level object is depth 1
        return b'{"asset":{"version":"2.0"},"x":' + b"[" * (depth - 1) + b"]" * (depth - 1) + b"}"
    put("archives/hostile/gltf-too-deep.astrapack", anim({"clips/deep.gltf": nested(129)}))
    put("archives/valid/animset-gltf-depth-128.astrapack", anim({"clips/deep.gltf": nested(128)}))
    # case folding is lower(upper(NFC(name))), full Unicode mappings: each pair names ONE file on NTFS/APFS
    for tag, a, b2 in (("long-s", "\u017f", "s"), ("micro", "\u00b5", "\u03bc"), ("final-sigma", "\u03c2", "\u03c3"),
                       ("dotless-i", "\u0131", "i"), ("kelvin", "\u212a", "k"), ("sharp-s", "\u00df", "ss"),
                       ("capital-sharp-s", "\u00df", "\u1e9e")):
        put(f"archives/hostile/name-fold-{tag}.astrapack",
            anim({f"clips/{a}.fbx": b"FBX-1", f"clips/{b2}.fbx": b"FBX-2"}))
    # N1: byte-order marks. three.js's TextDecoder strips a UTF-8 BOM, so a BOM-led glTF loads after a rename
    put("archives/hostile/gltf-json-utf8-bom.astrapack", anim({"clips/avatar.json": b"\xef\xbb\xbf" + avatar_json}))
    plain_gltf = json.dumps({"asset": {"version": "2.0"}}).encode()
    put("archives/hostile/gltf-with-bom.astrapack", anim({"clips/plain.gltf": b"\xef\xbb\xbf" + plain_gltf}))
    put("archives/hostile/gltf-json-utf16.astrapack",
        anim({"clips/avatar.json": b"\xff\xfe" + avatar_json.decode("utf-8").encode("utf-16-le")}))
    # N2: gltf 1.4.1 and browsers percent-decode a uri before joining it: %2f is a /
    pct_uri = "..%2f..%2f..%2f..%2fetc%2fpasswd"
    pct_gltf = json.dumps({"asset": {"version": "2.0"}, "buffers": [{"uri": pct_uri, "byteLength": 4}]}).encode()
    put("archives/hostile/pct.astrapack", anim({"clips/p.gltf": pct_gltf, f"clips/{pct_uri}": b"\x00\x01\x02\x03"}))
    # the sniff decides on the top-level `asset` key alone, whether or not the rest parses
    put("archives/hostile/gltf-sniff-garbage.astrapack", anim({"clips/x.json": b'{"asset":1,<garbage> \x00\x01 not json'}))
    # TWO faults, to pin the order (ingest-v1.md §3): an encrypted entry FIRST in directory order and a
    # zip64 extra field on a LATER one. The zip64 pre-pass over all entries runs before any step-3 check
    def two_faults(entries):
        for e in entries:
            if e["name"] == "clips/a.fbx":
                e["flags"] = 1
            if e["name"] == "clips/b.fbx":
                e["extra"] = struct.pack("<HHQQ", 0x0001, 16, 5, 5)
        return entries
    put("archives/hostile/order-zip64-before-encrypted.astrapack",
        bundle("astra.animpack", ASCII_PART, body=None, tweak=two_faults))
    hostile("audio-licence-undeclared.astrachar", bundle(
        "astra.character", {**CHAR_FILES, "characters/aiko/voice/hello.ogg": b"OggS" + b"\x00" * 24}, None))

    # games round 3 (astra-plugins-ops-42): a manifest that is not a JSON object must not crash
    # the reader -- `ingest_bundle` once called `.get` on whatever `strict_loads` returned
    def manifest_not_object(es):
        for e in es:
            if e["name"] == "astrachar.json":
                e["data"] = b"[]\n"
        return es
    hostile("manifest-not-object.astrachar", bundle("astra.character", model_files, BODY_PATH, tweak=manifest_not_object))

    # `images`/`buffers` must be arrays (bug: `"images": 5` raised TypeError in uri_refusal)
    images_not_array = json.dumps({"asset": {"version": "2.0"}, "images": 5}).encode()
    put("archives/hostile/gltf-images-not-array.astrapack", anim({"clips/badimg.gltf": images_not_array}))
    # `images` as a keyed OBJECT: a JS loader still reads the key "0", so the old code -- which only
    # walked LIST elements -- let an external uri through unseen (bug 3). The fix refuses the SHAPE,
    # so this is refused before the uri inside it is ever read
    images_as_object = json.dumps(
        {"asset": {"version": "2.0"}, "images": {"0": {"uri": "https://example.invalid/x.png"}}}).encode()
    put("archives/hostile/gltf-images-object.astrapack", anim({"clips/badimgobj.gltf": images_as_object}))

    # N2bis: `%` is legitimate glTF escaping (a space MUST be written `%20`) -- the old blanket
    # "no raw %" rule refused `Base%20Color.png`, a uri every real glTF exporter can emit
    space_png = b"\x89PNG\r\n\x1a\n" + b"SPACE-NAME-PNG"
    ok_pct_gltf = json.dumps({"asset": {"version": "2.0"}, "images": [{"uri": "Base%20Color.png"}]}).encode()
    put("archives/valid/animset-gltf-percent-space.astrapack",
        anim({"clips/pctok.gltf": ok_pct_gltf, "clips/Base Color.png": space_png}))
    # double percent-encoding: decoding ONCE must not be enough to reach `..` -- `%252e%252e`
    # decodes once to the literal text "%2e%2e", which still contains `%` and is refused outright
    # rather than decoded a second time (which would reach "..")
    dbl_gltf = json.dumps({"asset": {"version": "2.0"}, "buffers": [{"uri": "%252e%252e", "byteLength": 1}]}).encode()
    put("archives/hostile/gltf-percent-double-encoded.astrapack", anim({"clips/dbl.gltf": dbl_gltf}))
    # a malformed escape (not two hex digits) is refused, not silently passed through
    bad_pct_gltf = json.dumps({"asset": {"version": "2.0"}, "buffers": [{"uri": "%zz", "byteLength": 1}]}).encode()
    put("archives/hostile/gltf-percent-malformed.astrapack", anim({"clips/badpct.gltf": bad_pct_gltf}))

    # no bundle inside a content bundle: pack members are catalogue REFERENCES, never nested bytes.
    # `nested_bundle` is a whole, valid .astrachar -- the point is that content ingest refuses it by
    # its zip SIGNATURE alone, before it is ever opened as a sub-archive, whatever it is named
    nested_bundle = bundle("astra.character", MODEL_FILES, body=BODY_PATH)
    put("archives/hostile/nested-astrachar-in-astrapack.astrapack", anim({"clips/nested.astrachar": nested_bundle}))
    put("archives/hostile/nested-astrachar-renamed-dat.astrapack", anim({"clips/nested.dat": nested_bundle}))


# ── goldens too large to commit: built in memory, pinned by sha256 in vectors.json ──

MIB16 = 16 * 1024 * 1024


def _big_json(size: int) -> bytes:
    """A valid glTF JSON object of exactly `size` bytes."""
    head, tail = b'{"asset":{"version":"2.0"},"pad":"', b'"}'
    return head + b"a" * (size - len(head) - len(tail)) + tail


def _glb_of(json_bytes: bytes) -> bytes:
    j = json_bytes + b" " * (-len(json_bytes) % 4)
    return struct.pack("<4sII", b"glTF", 2, 20 + len(j)) + struct.pack("<I4s", len(j), b"JSON") + j


def _pack(extra: dict, stored=()) -> bytes:
    return bundle("astra.animpack", {**ASCII_PART, **extra}, body=None, methods={p: 0 for p in stored})


SYNTH = {
    # a GLB whose JSON chunk is over 16 MiB (ingest-v1.md §3 step 10)
    "glb-json-over-16mib": lambda: _pack({"clips/big.glb": _glb_of(_big_json(MIB16 + 4))}),
    # a .gltf over 16 MiB
    "gltf-over-16mib": lambda: _pack({"clips/big.gltf": _big_json(MIB16 + 1)}, stored=["clips/big.gltf"]),
    # B1: three .gltf, each readable (11 MiB), 33 MiB together: over the 32 MiB archive total
    "gltf-total-over-32mib": lambda: _pack({f"clips/g{i}.gltf": _big_json(11 * 1024 * 1024) for i in range(3)},
                                           stored=[f"clips/g{i}.gltf" for i in range(3)]),
}


def synth(name: str) -> bytes:
    return SYNTH[name]()


# ── SHA256SUMS ───────────────────────────────────────────────────────────

def sums() -> bytes:
    return "".join(f"{sha(OUT[p])}  {p}\n" for p in sorted(OUT)).encode("utf-8")


def build() -> dict[str, bytes]:
    OUT.clear()
    gen_part_digest()
    bundles = gen_bundles()
    cmds = gen_commands()
    gen_index(cmds, bundles)
    gen_withdrawn(cmds, bundles)
    gen_trust()
    gen_archives()
    OUT["SHA256SUMS"] = sums()
    return dict(OUT)


HAND_WRITTEN = {"README.md", "vectors.json", "gen.py"}


def main(argv: list[str]) -> int:
    want = build()
    if "--check" in argv:
        drift = [p for p, b in want.items() if not (HERE / p).is_file() or (HERE / p).read_bytes() != b]
        on_disk = {p.relative_to(HERE).as_posix() for p in HERE.rglob("*")
                   if p.is_file() and "__pycache__" not in p.parts}
        extra = sorted(on_disk - set(want) - HAND_WRITTEN)
        if drift or extra:
            print("testdata/content/gen.py: DRIFT: " + ", ".join(drift + [f"{e} (not generated)" for e in extra]))
            print("  run: python3 testdata/content/gen.py")
            return 1
        print(f"testdata/content/gen.py: {len(want)} generated files current (SHA256SUMS included).")
        return 0
    for p, b in want.items():
        dest = HERE / p
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b)
    print(f"testdata/content/gen.py: wrote {len(want)} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
