#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Minice — https://minice.ai
"""Stdlib-only primitives the content-catalogue contract (spec/content/) needs:
RFC 8785 JCS for the documents this spec defines, the signing digest of the
plugin envelope, the part digest, and Ed25519 (RFC 8032 §5.1) sign/verify.

Why a hand-written Ed25519: the `content-spec` CI job installs nothing, the
same rule `tools/schemalite.py` follows, and the goldens under
testdata/content/ are REAL signed envelopes so that the client (L8) and the
signer (L4) can test domain separation and kind scoping against bytes, not
against prose. This is the RFC 8032 reference algorithm, slow and fine for a
few dozen signatures. It is a TEST tool: it is not constant-time, and nothing
outside testdata/content/ may ever be signed with it.

`verify` is STRICT in the sense spec/content/trust-kind-keys-v1.md §5 asks
for (`ed25519_dalek::verify_strict`): S must be < L, both points must decode
canonically, and a small-order public key or R is refused.
"""

from __future__ import annotations

import base64
import hashlib
import json
import unicodedata
from typing import Any

# ── JCS (RFC 8785), for the value space these documents use ──────────────
#
# The content documents carry strings, integers, booleans, null, arrays and
# objects. They never carry a float (spec/content/common-v1.md §1: every
# number is an integer), so the number branch refuses one instead of
# implementing ECMAScript's shortest round-trip, which nothing here needs.


def _jcs_str(s: str) -> str:
    out = ['"']
    for ch in s:
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\b":
            out.append("\\b")
        elif ch == "\f":
            out.append("\\f")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif o < 0x20:
            out.append(f"\\u{o:04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def jcs(value: Any) -> bytes:
    """RFC 8785 canonical bytes (UTF-8)."""
    return _jcs(value).encode("utf-8")


def _jcs(v: Any) -> str:
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        raise ValueError("a float has no place in a content document (common-v1.md §1)")
    if isinstance(v, str):
        return _jcs_str(v)
    if isinstance(v, list):
        return "[" + ",".join(_jcs(x) for x in v) + "]"
    if isinstance(v, dict):
        # RFC 8785 §3.2.3: members sorted by their names' UTF-16 code units.
        keys = sorted(v.keys(), key=lambda k: k.encode("utf-16-be"))
        return "{" + ",".join(_jcs_str(k) + ":" + _jcs(v[k]) for k in keys) + "}"
    raise TypeError(f"not a JSON value: {type(v).__name__}")


def signing_digest(domain: str, signed: Any) -> bytes:
    """SHA-256(domain ‖ 0x00 ‖ JCS(signed)) — docs/en/spec/registry-index.md
    §2, the plugin envelope this spec reuses unchanged."""
    return hashlib.sha256(domain.encode("utf-8") + b"\x00" + jcs(signed)).digest()


# ── the part digest (spec/content/part-digest-v1.md) ─────────────────────


def path_refusal(path: str) -> str | None:
    """None when `path` is a canonical ZIP ENTRY NAME, else the rule it breaks
    (part-digest-v1.md §2). The ingest refuses the BUNDLE on any of these
    (E_ARCHIVE_NAME_UNSAFE), so a stored name is already canonical. `empty` is
    about entry names: the derived path `""` of a single-file part (§3) is not an
    entry name and never passes through here."""
    if path == "":
        return "empty"
    if unicodedata.normalize("NFC", path) != path:
        return "not-nfc"
    if "\\" in path:
        return "backslash"
    if path.startswith("/"):
        return "leading-slash"
    for ch in path:
        o = ord(ch)
        if o <= 0x1F or 0x7F <= o <= 0x9F:
            return "control-character"
    for seg in path.split("/"):
        if seg == "":
            return "empty-segment"
        if seg == "..":
            return "dot-dot"
    return None


def part_digest_pairs(files: dict[str, bytes], *, root: str | None) -> list[list[str]]:
    """files: {ZIP ENTRY NAME: bytes} of ONE part. Paths are made relative to the PART ROOT
    (part-digest-v1.md §2): `root` is the part's own directory (`animpacks/<id>`, an accessory's
    folder; `""` for a pack at the zip root of a `.astrapack`), or None for a SINGLE-FILE part,
    whose one pair has the path `""` -- so its digest depends on its bytes alone."""
    for p in files:
        why = path_refusal(p)
        if why is not None:
            raise ValueError(f"{p!r}: {why}")
    if root is None:
        if len(files) != 1:
            raise ValueError("a single-file part holds exactly one file")
        return [["", hashlib.sha256(next(iter(files.values()))).hexdigest()]]
    prefix = root.rstrip("/") + "/" if root else ""
    pairs = []
    for p, b in files.items():
        if not p.startswith(prefix):
            raise ValueError(f"{p!r} is not under the part root {root!r}")
        pairs.append([p[len(prefix):], hashlib.sha256(b).hexdigest()])
    pairs.sort(key=lambda pr: pr[0].encode("utf-8"))
    return pairs


def part_digest(files: dict[str, bytes], *, root: str | None) -> str:
    """The part digest (bare lowercase hex) of ONE part; see part_digest_pairs."""
    return hashlib.sha256(jcs(part_digest_pairs(files, root=root))).hexdigest()


# ── Ed25519, RFC 8032 §5.1 reference (test use only) ──────────────────────

_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _inv(x: int) -> int:
    return pow(x, _P - 2, _P)


def _xrecover(y: int, sign: int) -> int | None:
    if y >= _P:
        return None
    xx = (y * y - 1) * _inv(_D * y * y + 1) % _P
    if xx == 0:
        return None if sign else 0
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P != 0:
        x = x * _I % _P
    if (x * x - xx) % _P != 0:
        return None
    if x & 1 != sign:
        x = _P - x
    return x


_GY = 4 * _inv(5) % _P
_GX = _xrecover(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)
_ZERO = (0, 1, 1, 0)


def _add(a, b):
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    A = (y1 - x1) * (y2 - x2) % _P
    B = (y1 + x1) * (y2 + x2) % _P
    C = 2 * t1 * t2 * _D % _P
    Dd = 2 * z1 * z2 % _P
    E, F, G, H = B - A, Dd - C, Dd + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _mul(s: int, p):
    q = _ZERO
    while s > 0:
        if s & 1:
            q = _add(q, p)
        p = _add(p, p)
        s >>= 1
    return q


def _eq(a, b) -> bool:
    return (a[0] * b[2] - b[0] * a[2]) % _P == 0 and (a[1] * b[2] - b[1] * a[2]) % _P == 0


def _encode(p) -> bytes:
    zi = _inv(p[2])
    x, y = p[0] * zi % _P, p[1] * zi % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decode(b: bytes):
    if len(b) != 32:
        return None
    n = int.from_bytes(b, "little")
    y, sign = n & ((1 << 255) - 1), n >> 255
    x = _xrecover(y, sign)
    if x is None:
        return None
    p = (x, y, 1, x * y % _P)
    if _encode(p) != b:  # canonical encoding only
        return None
    return p


def _small_order(p) -> bool:
    return _eq(_mul(8, p), _ZERO)


def _sha512_int(*parts: bytes) -> int:
    return int.from_bytes(hashlib.sha512(b"".join(parts)).digest(), "little")


def _expand(seed: bytes):
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(seed: bytes) -> bytes:
    a, _ = _expand(seed)
    return _encode(_mul(a, _G))


def sign(seed: bytes, msg: bytes) -> bytes:
    a, prefix = _expand(seed)
    pk = _encode(_mul(a, _G))
    r = _sha512_int(prefix, msg) % _L
    R = _encode(_mul(r, _G))
    k = _sha512_int(R, pk, msg) % _L
    s = (r + k * a) % _L
    return R + int.to_bytes(s, 32, "little")


def verify(pk: bytes, msg: bytes, sig: bytes) -> bool:
    if len(sig) != 64 or len(pk) != 32:
        return False
    A = _decode(pk)
    R = _decode(sig[:32])
    if A is None or R is None or _small_order(A) or _small_order(R):
        return False
    s = int.from_bytes(sig[32:], "little")
    if s >= _L:
        return False
    k = _sha512_int(sig[:32], pk, msg) % _L
    return _eq(_mul(s, _G), _add(R, _mul(k, A)))


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def unb64(s: str) -> bytes | None:
    try:
        return base64.b64decode(s, validate=True)
    except (ValueError, TypeError):
        return None


def test_seed(name: str) -> bytes:
    """The deterministic seed of a published TEST key. These keys are in the
    clear on purpose; trusting one anywhere but testdata/content/ is a bug."""
    return hashlib.sha256(b"astra-content-TEST-KEY-never-trusted:" + name.encode("utf-8")).digest()


class DuplicateMember(ValueError):
    pass


def _no_dupes(pairs):
    seen = {}
    for k, v in pairs:
        if k in seen:
            raise DuplicateMember(k)
        seen[k] = v
    return seen


def strict_loads(text: str | bytes) -> Any:
    """json.loads that REFUSES a duplicate member name anywhere
    (common-v1.md §1): last-wins and first-wins readers would otherwise
    see different documents behind one valid signature."""
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    return json.loads(text, object_pairs_hook=_no_dupes)


def _escape_hidden_controls(text: str) -> str:
    """Every C0 control (other than the JSON structural `\\n`), DEL (U+007F)
    and C1 control (U+0080-U+009F) as a `\\uXXXX` escape, never a raw byte: a
    raw one trips the minice repository's own "no hidden control character in
    any tracked text file" gate, and refuses the whole file on every
    repository that vendors this one. The parsed value is unchanged -- only
    the on-disk spelling moves (`tools/check-no-hidden-controls.py`)."""
    out = []
    for c in text:
        cp = ord(c)
        if cp != 0x0A and (cp <= 0x1F or cp == 0x7F or 0x80 <= cp <= 0x9F):
            out.append(f"\\u{cp:04x}")
        else:
            out.append(c)
    return "".join(out)


def pretty(doc: Any) -> str:
    """The committed spelling of every generated JSON golden."""
    return _escape_hidden_controls(json.dumps(doc, ensure_ascii=False, indent=2)) + "\n"
