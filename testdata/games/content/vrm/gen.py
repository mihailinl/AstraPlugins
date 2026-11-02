# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Minice — https://minice.ai
"""Regenerates every VRM gate golden in this directory, deterministically.

Each golden is a GLB holding one JSON chunk and nothing else: enough for
manifest.md §2.7.3's gate, which reads only the VRM 0.x and VRM 1.0 metas.
Two serialisations are in use, kept as they were first written so that the
bytes (and the digests other repositories pin) do not move: `plain` is
json.dumps' default, `compact` is sorted keys with no spaces. The hostile
`E_CONTENT_FORMAT` goldens are written from literal JSON text (`raw`), since
json.dumps cannot name a member twice; `past-eof` declares a JSON chunk 8
bytes longer than the file and `bad-length` a header length 4 bytes short.

It also writes the release goldens' content files that are not hand-written
text (`RELEASE_FILES`, under ../releases/), and `synth(name)` builds the ones
too large to commit -- check-games-goldens.py calls it and compares the bytes
with the sha256 vectors.json pins, as the content catalogue's gen.py does.

    python3 gen.py           # write every file
    python3 gen.py --check   # write nothing; fail if any file differs
"""
import codecs
import functools
import json
import pathlib
import struct
import sys
import zlib

HERE = pathlib.Path(__file__).resolve().parent

V0_ALLOWED = {"licenseName": "CC_BY", "allowedUserName": "Everyone",
              "violentUssageName": "Disallow", "sexualUssageName": "Disallow", "commercialUssageName": "Allow"}
V1_ALLOWED = {"allowRedistribution": True, "avatarPermission": "everyone",
              "allowExcessivelyViolentUsage": False, "allowExcessivelySexualUsage": False,
              "allowPoliticalOrReligiousUsage": True, "allowAntisocialOrHateUsage": False}


def v0(meta):
    return {"extensions": {"VRM": {"meta": meta}}}


def v1(meta):
    return {"extensions": {"VRMC_vrm": {"meta": meta}}}


def both(meta0, meta1):
    return {"asset": {"version": "2.0"},
            "extensions": {"VRM": {"meta": meta0}, "VRMC_vrm": {"meta": meta1, "specVersion": "1.0"}},
            "extensionsUsed": ["VRM", "VRMC_vrm"]}


GOLDENS = {
    # accept
    "allowed.vrm": ("plain", v0(V0_ALLOWED)),
    "allowed-vrm1.vrm": ("plain", v1(V1_ALLOWED)),
    "vrm-metas-agree.vrm": ("compact", both(
        {**V0_ALLOWED},
        {"allowAntisocialOrHateUsage": False, "allowExcessivelySexualUsage": False, "allowExcessivelyViolentUsage": False,
         "allowPoliticalOrReligiousUsage": True, "allowRedistribution": True, "avatarPermission": "everyone"})),
    # refuse
    # licenseName here is no UniVRM token (an unknown reading); the permission refuses whatever it
    # says, so these two keep the bytes other repositories already pin.
    "refused-vrm0-only-author.vrm": ("plain", v0({"licenseName": "Redistribution_Allowed", "allowedUserName": "OnlyAuthor"})),
    "refused-vrm1-only-author.vrm": ("plain", v1({"allowRedistribution": True, "avatarPermission": "onlyAuthor"})),
    "refused-vrm0-named-people.vrm": ("plain", v0({"licenseName": "Redistribution_Allowed", "allowedUserName": "ExplicitlyLicensedPerson"})),
    "refused-vrm1-named-people.vrm": ("plain", v1({"allowRedistribution": True, "avatarPermission": "onlySeparatelyLicensedPerson"})),
    "refused-vrm0-redistribution-prohibited.vrm": ("plain", v0({"licenseName": "Redistribution_Prohibited", "allowedUserName": "Everyone"})),
    "refused-vrm1-redistribution-false.vrm": ("plain", v1({"allowRedistribution": False, "avatarPermission": "everyone"})),
    "refused-vrm1-redistribution-string.vrm": ("plain", v1({"allowRedistribution": "true", "avatarPermission": "everyone"})),
    "refused-vrm0-absent-fields.vrm": ("plain", v0({})),
    "refused-vrm1-absent-fields.vrm": ("plain", v1({})),
    # unknown: never Allowed, never refused by the gate
    "unknown-no-meta.vrm": ("plain", {"asset": {"version": "2.0"}}),
    "unknown-vrm0-licence-other.vrm": ("plain", v0({"licenseName": "Other", "allowedUserName": "Everyone"})),
    "unknown-vrm0-licence-unrecognised.vrm": ("plain", v0({"licenseName": "Redistribution_Allowed", "allowedUserName": "Everyone"})),
    "unknown-vrm0-user-unrecognised.vrm": ("plain", v0({"licenseName": "CC0", "allowedUserName": "Anyone"})),
    "unknown-vrm1-avatar-unrecognised.vrm": ("plain", v1({"allowRedistribution": True, "avatarPermission": "anyone"})),
    # E_CONTENT_FORMAT: every GLB, in any part and of any class
    "vrm-duplicate-key.vrm": ("raw", '{"extensions": {"VRMC_vrm": {"meta": {"allowRedistribution": false, '
                                     '"avatarPermission": "everyone", "allowRedistribution": true}}}}'),
    "glb-duplicate-extensions.glb": ("raw", '{"extensions": {"VRMC_vrm": {"meta": {"allowRedistribution": false, '
                                            '"avatarPermission": "everyone"}}}, "extensions": {}}'),
    "vrm-chunk-past-eof.vrm": ("past-eof", json.dumps(v0(V0_ALLOWED))),
    "vrm-header-length-wrong.vrm": ("bad-length", json.dumps(v0(V0_ALLOWED))),
    "glb-remote-uri.glb": ("plain", {"asset": {"version": "2.0"}, "images": [{"uri": "https://example.invalid/t.png"}]}),
    "glb-data-uri.glb": ("plain", {"asset": {"version": "2.0"}, "images": [{"uri": "data:image/png;base64,iVBORw0KGgo="}]}),
    # conflict
    "vrm-metas-disagree.vrm": ("compact", both(
        {**V0_ALLOWED}, {"allowRedistribution": False, "avatarPermission": "everyone"})),
    "vrm-metas-unknown-vs-allowed.vrm": ("compact", both(
        {**V0_ALLOWED, "licenseName": "Other"}, {"allowRedistribution": True, "avatarPermission": "everyone"})),
}


def glb(style, obj):
    if style == "plain":
        text = json.dumps(obj)
    elif style == "compact":
        text = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    else:
        text = obj
    chunk = text.encode("utf-8")
    chunk += b" " * ((-len(chunk)) % 4)
    declared = len(chunk) + (8 if style == "past-eof" else 0)
    body = struct.pack("<I4s", declared, b"JSON") + chunk
    total = 12 + len(body) - (4 if style == "bad-length" else 0)
    return struct.pack("<4sII", b"glTF", 2, total) + body


# ── the release goldens (../releases/<name>/...) ────────────────────────

MIB = 1024 * 1024


def gltf_text(obj) -> bytes:
    return json.dumps(obj).encode("utf-8")


# a text glTF carrying an avatar whose licence refuses redistribution
PLAIN_GLTF = {"asset": {"version": "2.0"}}
GLTF_AVATAR_PROHIBITED = {"asset": {"version": "2.0"},
                          **v0({"licenseName": "Redistribution_Prohibited", "allowedUserName": "Everyone"})}

PCT_URI = "..%2f..%2f..%2f..%2fetc%2fpasswd"

RELEASE_FILES = {
    # content by bytes (manifest.md §2.7.1): a GLB or a text glTF under any other name
    "releases/glb-named-bin/data/avatar.bin": lambda: glb(*GOLDENS["refused-vrm0-redistribution-prohibited.vrm"]),
    # only the release ROOT's astra-gi.toml is the manifest; one in a folder is a file like any other
    "releases/vrm-named-manifest-nested/models/astra-gi.toml": lambda: glb(*GOLDENS["refused-vrm0-redistribution-prohibited.vrm"]),
    "releases/gltf-named-json/data/avatar.json": lambda: gltf_text(GLTF_AVATAR_PROHIBITED),
    "releases/gltf-named-json-utf16/data/avatar.json":
        lambda: codecs.BOM_UTF16_LE + json.dumps(GLTF_AVATAR_PROHIBITED).encode("utf-16-le"),
    # ... and what a game integration really ships beside it, accepted
    "releases/localisation-utf16/lang/strings.json":
        lambda: codecs.BOM_UTF16_LE + '{"greeting": "Привет", "farewell": "Пока"}'.encode("utf-16-le"),
    "releases/localisation-utf16/lang/credits.txt": lambda: codecs.BOM_UTF16_BE + "Спасибо\n".encode("utf-16-be"),
    "releases/json-nested-asset/data/config.json": lambda: gltf_text({"meta": {"asset": "props/crate"}}),
    # a top-level asset that is not an object: three.js reads asset.version, so this is no glTF
    "releases/json-asset-string/data/hero.json": lambda: gltf_text({"asset": "textures/hero.png", "scale": 2}),
    # a .gltf uri a loader percent-decodes BEFORE it joins: it leaves the release, though a file with
    # that literal name is right beside it (the content catalogue's pct, N2)
    "releases/gltf-uri-percent/models/prop.gltf":
        lambda: gltf_text({"asset": {"version": "2.0"}, "buffers": [{"uri": PCT_URI, "byteLength": 4}]}),
    f"releases/gltf-uri-percent/models/{PCT_URI}": lambda: b"\x00\x01\x02\x03",
    # glTF 2.0 percent-encodes a space: Base%20Color.bin names "Base Color.bin", which is present
    "releases/gltf-uri-space-encoded/models/prop.gltf": lambda: gltf_text(
        {"asset": {"version": "2.0"}, "buffers": [{"uri": "data/Base%20Color.bin", "byteLength": 4}]}),
    "releases/gltf-uri-space-encoded/models/data/Base Color.bin": lambda: b"\x00\x01\x02\x03",
    # %252e%252e/ decodes ONCE to the text %2e%2e/: decoded again it would climb out; a literal file of
    # that once-decoded name is present, so only the double-encoding rule refuses it
    "releases/gltf-uri-double-encoded/models/prop.gltf": lambda: gltf_text(
        {"asset": {"version": "2.0"}, "buffers": [{"uri": "%252e%252e/secret.bin", "byteLength": 4}]}),
    "releases/gltf-uri-double-encoded/models/%2e%2e/secret.bin": lambda: b"\x00\x01\x02\x03",
    # the caps (ingest-v1.md §3 step 10): nesting deeper than 128, the top-level object being 1
    "releases/gltf-too-deep/models/prop.gltf": lambda: deep_gltf(129),
    "releases/gltf-depth-128/models/prop.gltf": lambda: deep_gltf(128),
    # glTF 2.0 is UTF-8 JSON without a byte-order mark
    "releases/gltf-with-bom/models/prop.gltf": lambda: codecs.BOM_UTF8 + gltf_text(PLAIN_GLTF),
    "releases/gltf-utf16/models/prop.gltf": lambda: codecs.BOM_UTF16_LE + json.dumps(PLAIN_GLTF).encode("utf-16-le"),
}


def deep_gltf(depth: int) -> bytes:
    """A .gltf whose JSON nests exactly `depth` deep: the object, then arrays."""
    return b'{"asset": {"version": "2.0"}, "extras": ' + b"[" * (depth - 1) + b"]" * (depth - 1) + b"}"


def padded_glb(chunk_len: int) -> bytes:
    """A whole GLB whose one JSON chunk is a plain glTF padded with spaces to `chunk_len` bytes."""
    text = gltf_text(PLAIN_GLTF)
    chunk = text + b" " * (chunk_len - len(text))
    return struct.pack("<4sII", b"glTF", 2, 20 + len(chunk)) + struct.pack("<I4s", len(chunk), b"JSON") + chunk


SYNTH = {
    # over the 16 MiB a key-by-key sniff reads: refused only when the bytes name "asset"
    "json-over-16mib-nested-asset": lambda: b'{"meta": {"asset": {}}, "strings": "' + b"x" * (16 * MIB) + b'"}',
    "json-over-16mib-plain": lambda: b'{"strings": "' + b"x" * (16 * MIB) + b'"}',
    # a 32 MiB game archive that happens to begin FF FE, then lone surrogates: decoded whole it
    # is ~80 MB of str and UTF-8 for a test of its first character
    "pak-utf16-bom": lambda: b"\xff\xfe" + b"\x00\xd8" * (16 * MIB),
    # 16 MiB of {"":0,"":0,...}: the per-character sniff reads it at ~4 MiB a second
    "json-16mib-many-keys": lambda: b"{" + b'"":0,' * (16 * MIB // 5 - 1) + b'"":0}',
    # the caps, each checked BEFORE anything is parsed
    "glb-json-over-16mib": lambda: padded_glb(16 * MIB + 4),
    "gltf-over-16mib": lambda: gltf_text(PLAIN_GLTF) + b" " * (16 * MIB),
    "glb-json-11mib": lambda: padded_glb(11 * MIB),  # three of them: each under 16 MiB, together over 32
    # a million levels: a recursive parser raises, and that must be a refusal, never a crash
    "gltf-million-deep": lambda: deep_gltf(1_000_000),
}


# the content catalogue's own bundles, byte for byte, inside a game integration's release:
# judged by that contract's own code (manifest.md §2.7.3), so they must stay its exact bytes
CONTENT_ARCHIVES = HERE.parents[2] / "content" / "archives"
BUNDLE_COPIES = {
    "releases/bundle-vrm-redistribution-prohibited/characters/scout.astrachar": "hostile/vrm-redistribution-prohibited.astrachar",
    "releases/bundle-glb-prohibited-beside-allowed-body/characters/scout.astrachar":
        "hostile/glb-prohibited-beside-allowed-body.astrachar",
    "releases/bundle-vrm-metas-disagree/characters/scout.astrachar": "hostile/vrm-metas-disagree.astrachar",
    "releases/bundle-gap-between-entries/characters/scout.astrachar": "hostile/gap-between-entries.astrachar",
    "releases/bundle-vrm0-licence-other/characters/scout.astrachar": "hostile/vrm0-licence-other.astrachar",
    "releases/bundle-animset-wave/packs/wave.astrapack": "valid/animset-wave.astrapack",
    "releases/bundle-model-aiko/characters/aiko.astrachar": "valid/model-aiko.astrachar",
    "releases/bundle-renamed/packs/wave.zip": "valid/animset-wave.astrapack",
    "releases/bundle-audio-licence-undeclared/characters/scout.astrachar": "hostile/audio-licence-undeclared.astrachar",
}
for _rel, _src in BUNDLE_COPIES.items():
    RELEASE_FILES[_rel] = (lambda src: lambda: (CONTENT_ARCHIVES / src).read_bytes())(_src)


@functools.lru_cache(maxsize=1)
def content_gen():
    """testdata/content/gen.py, whose bundle builders make the embedded bundles below."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("content_gen", HERE.parents[2] / "content" / "gen.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── a game's own archives (manifest.md §2.7.1): zips that are not bundles, built with the content
# catalogue's own zip writer ──────────────────────────────────────────────────────────────────────

PNG16 = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
MANIFEST_MF = b"Manifest-Version: 1.0\r\nCreated-By: gen.py\r\n"


DOS_TIME, DOS_DATE = 0, ((2026 - 1980) << 9) | (1 << 5) | 1  # 2026-01-01 00:00


def stored_deflate(data: bytes) -> bytes:
    """A Deflate stream made of stored blocks only (RFC 1951 §3.2.4): valid
    Deflate that any inflater reads, written without a compressor, so these
    bytes cannot move when someone's compressor does."""
    if not data:
        return b"\x01\x00\x00\xff\xff"
    out = bytearray()
    for at in range(0, len(data), 0xFFFF):
        block = data[at:at + 0xFFFF]
        out += bytes([1 if at + 0xFFFF >= len(data) else 0]) + struct.pack("<HH", len(block), len(block) ^ 0xFFFF) + block
    return bytes(out)


def zip_of(entries: list[dict]) -> bytes:
    """Games' own zip writer, for every zip and bundle these goldens build:
    each entry Stored, or -- where a golden needs a Deflated entry -- Deflate
    written as stored blocks. Never the content catalogue's compressor: #130
    replaced it once and moved every byte built on it. Entries are {name,
    data, method=0|8, extra, pad_before}; files are regular (unix 0644)."""
    out, central = bytearray(), bytearray()
    for e in entries:
        out += e.get("pad_before", b"")
        off = len(out)
        name = e["name"].encode("utf-8")
        data = e.get("data", b"")
        method = e.get("method", 0)
        comp = stored_deflate(data) if method == 8 else data
        crc = zlib.crc32(data) & 0xFFFFFFFF
        extra = e.get("extra", b"")
        flags = 0x800 if any(c > 0x7F for c in name) else 0
        out += struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, flags, method, DOS_TIME, DOS_DATE,
                           crc, len(comp), len(data), len(name), len(extra)) + name + extra + comp
        central += struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, (3 << 8) | 20, 20, flags, method, DOS_TIME, DOS_DATE,
                               crc, len(comp), len(data), len(name), len(extra), 0, 0, 0, 0o100644 << 16, off) + name + extra
    cd_off = len(out)
    out += central
    out += struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(entries), len(entries), len(central), cd_off, 0)
    return bytes(out)


def jar(entries: list[dict]) -> bytes:
    return zip_of(entries)


def stored_bundle(fmt: str, files: dict) -> bytes:
    """A content bundle in the content catalogue's own format (its
    bundle_entries: the files, then astrachar.json listing their digests),
    every entry Stored and written by zip_of. The 32 MiB budget these feed is
    about glTF JSON size, never about compression."""
    return zip_of([dict(e, method=0) for e in content_gen().bundle_entries(fmt, files, body=None)])


def avatar_jar(vrm: bytes, name: str = "assets/avatar.vrm", **tweak) -> bytes:
    """A mod jar: a manifest and a Deflated .png (a bundle would have to store it), and a VRM."""
    entries = [{"name": "META-INF/MANIFEST.MF", "data": MANIFEST_MF, "method": 8},
               {"name": "assets/logo.png", "data": PNG16, "method": 8},
               {"name": name, "data": vrm, "method": 0}]
    for e in entries:
        e.update(tweak.get(e["name"], {}))
    return jar(entries)


ALLOWED_VRM = lambda: glb(*GOLDENS["allowed.vrm"])  # noqa: E731
PROHIBITED_VRM = lambda: glb(*GOLDENS["refused-vrm0-redistribution-prohibited.vrm"])  # noqa: E731
Z64_EXTRA = struct.pack("<HHQQ", 0x0001, 16, 1, 1)  # a zip64 extended-information field

RELEASE_FILES.update({
    "releases/jar-vrm-undeclared/mods/avatar.jar": lambda: avatar_jar(ALLOWED_VRM()),
    "releases/jar-vrm-declared/mods/avatar.jar": lambda: avatar_jar(ALLOWED_VRM()),
    "releases/jar-vrm-prohibited/mods/avatar.jar": lambda: avatar_jar(PROHIBITED_VRM()),
    "releases/jar-glb-named-bin/mods/avatar.jar": lambda: avatar_jar(PROHIBITED_VRM(), name="assets/avatar.bin"),
    # a gap before the VRM's local header, where a cloaked entry hides (the content catalogue's gap-between-entries)
    "releases/jar-cloaked/mods/avatar.jar":
        lambda: avatar_jar(ALLOWED_VRM(), **{"assets/avatar.vrm": {"pad_before": b"PK\x03\x04HIDDEN-ENTRY"}}),
    # zip64 (as a modpack past 65,535 entries or 4 GiB needs): not opened, flagged
    "releases/jar-zip64/mods/big.jar":
        lambda: avatar_jar(PROHIBITED_VRM(), **{"META-INF/MANIFEST.MF": {"extra": Z64_EXTRA}}),
    # a jar inside a jar (Fabric's META-INF/jars/, Forge's jarjar): one level deep, flagged
    "releases/jar-in-jar/mods/outer.jar": lambda: jar([
        {"name": "META-INF/MANIFEST.MF", "data": MANIFEST_MF, "method": 8},
        {"name": "META-INF/jars/inner.jar", "data": avatar_jar(PROHIBITED_VRM()), "method": 0}]),
})

# 5,000 entries: past the content catalogue's 4,096, within a game archive's 65,536
SYNTH["jar-5000-entries"] = lambda: jar([{"name": f"assets/lang/{i}.txt", "data": b"x"} for i in range(5000)])

SYNTH["astrapack-gltf-11mib"] = lambda: stored_bundle(  # three of them: 33 MiB
    "astra.animpack", {**content_gen().ASCII_PART, "clips/g.gltf": content_gen()._big_json(11 * MIB)})


@functools.lru_cache(maxsize=4)
def synth(name: str) -> bytes:
    """The release goldens too large to commit, built in memory (one copy of
    each, however many files of a golden share it)."""
    return SYNTH[name]()


def main(argv):
    check = "--check" in argv
    bad = []
    for name, (style, obj) in GOLDENS.items():
        want = glb(style, obj)
        path = HERE / name
        if check:
            if not path.exists() or path.read_bytes() != want:
                bad.append(name)
        else:
            path.write_bytes(want)
    for rel, build in RELEASE_FILES.items():
        want = build()
        path = HERE.parent / rel
        if check:
            if not path.exists() or path.read_bytes() != want:
                bad.append(rel)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(want)
    if check:
        stray = sorted(p.name for p in [*HERE.glob("*.vrm"), *HERE.glob("*.glb")] if p.name not in GOLDENS)
        for name in bad:
            print(f"FAIL {name} is not what gen.py writes", file=sys.stderr)
        for name in stray:
            print(f"FAIL {name} is not written by gen.py", file=sys.stderr)
        if bad or stray:
            return 1
        print(f"ok   {len(GOLDENS)} VRM goldens and {len(RELEASE_FILES)} release files are what gen.py writes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
