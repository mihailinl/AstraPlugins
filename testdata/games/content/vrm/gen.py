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

    python3 gen.py           # write every file
    python3 gen.py --check   # write nothing; fail if any file differs
"""
import json
import pathlib
import struct
import sys

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
    if check:
        stray = sorted(p.name for p in [*HERE.glob("*.vrm"), *HERE.glob("*.glb")] if p.name not in GOLDENS)
        for name in bad:
            print(f"FAIL {name} is not what gen.py writes", file=sys.stderr)
        for name in stray:
            print(f"FAIL {name} is not written by gen.py", file=sys.stderr)
        if bad or stray:
            return 1
        print(f"ok   {len(GOLDENS)} VRM goldens are what gen.py writes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
