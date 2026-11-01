#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Minice — https://minice.ai
"""Writes spec/content/schemas/*.json — GENERATED, never hand-edit them.

Eleven schema files share most of their definitions (the envelope, the base
entry fields, the licence object, the withdrawn row). Eleven hand-kept copies
of one definition are eleven places for it to drift, which is the defect the
estate's "Content may differ. Code may not." rule exists to stop; so the
definitions live once, here, and `--check` (run by the `content-spec` CI job)
fails when a committed file is not what this script writes.

Every file uses only the keyword subset tools/schemalite.py implements
(tools/test_schemalite.py walks them). Cross-field rules a JSON Schema cannot
express (security => act security, a model's single part, the not_before
order) are NOT here: they are tools/check-content-goldens.py's named
semantic rules, and each spec says which rule is which.

    python3 tools/gen-content-schemas.py           # write
    python3 tools/gen-content-schemas.py --check   # exit 1 on drift
"""

from __future__ import annotations

import copy
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "spec" / "content" / "schemas"
BASE_ID = "https://astraplugins.minice.ai/spec/content/schemas/"

KINDS = ["commands", "characters", "models", "animsets", "packs"]
KEY_KINDS = KINDS + ["games"]

MIB = 1024 * 1024

# ── shared definitions ───────────────────────────────────────────────────

SHA256 = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
# spec/reserved-ids.yaml `id_pattern`, the plugin id shape; the `--` rule that
# file states beside it is semantic (check-content-goldens.py `id-double-hyphen`).
ITEM_ID = {"type": "string", "pattern": "^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])$"}
SEMVER = {
    "type": "string",
    "maxLength": 64,
    # SemVer 2.0.0: a numeric pre-release identifier has no leading zero
    "pattern": "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)"
               "(-(0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)(\\.(0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?$",
}
# v1's range grammar: comma-joined comparators `<` `<=` `>` `>=` `=` (or none) before a version
# (OPEN.md O-19). A caret, tilde, wildcard or `||` is a later contract version, never a silent widening.
_CMP = "(<=|>=|<|>|=)?[0-9A-Za-z.-]+"
VERSION_RANGE = {"type": "string", "minLength": 1, "maxLength": 128, "pattern": f"^{_CMP}( *, *{_CMP})*$"}
UNIX = {"type": "integer", "minimum": 0}
HTTPS = {"type": "string", "maxLength": 2048, "pattern": "^https://[^\\s]+$"}
TEXT_ID = {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{0,63}$"}

DEFS_COMMON = {
    "sha256": SHA256,
    "itemId": ITEM_ID,
    "semver": SEMVER,
    "versionRange": VERSION_RANGE,
    "unixSeconds": UNIX,
    "https": HTTPS,
    "httpsOrNull": {"anyOf": [{"$ref": "#/$defs/https"}, {"type": "null"}]},
    "signature": {
        "type": "object",
        "required": ["key_id", "sig"],
        "additionalProperties": False,
        "properties": {
            "key_id": {"type": "string", "minLength": 1, "maxLength": 64},
            "sig": {"type": "string", "pattern": "^[A-Za-z0-9+/]{86}==$"},
        },
    },
}

LISTING = {
    "type": "object",
    "minProperties": 1,
    "maxProperties": 16,
    "propertyNames": {"pattern": "^[a-z]{2,3}(-[A-Z]{2})?$"},
    "additionalProperties": {
        "type": "object",
        "required": ["title", "description"],
        "additionalProperties": False,
        "properties": {
            # spec/listing-limits.yaml max_name_length / max_description_length
            "title": {"type": "string", "minLength": 1, "maxLength": 64},
            "description": {"type": "string", "maxLength": 4000},
        },
    },
}

THUMBNAIL = {
    "type": "object",
    "required": ["sha256", "size"],
    "additionalProperties": False,
    "properties": {"sha256": {"$ref": "#/$defs/sha256"}, "size": {"type": "integer", "minimum": 1, "maximum": MIB}},
}

TRI = {"enum": ["allowed", "prohibited", "unknown"]}

LICENCE = {
    "type": "object",
    "required": [
        "source", "spec", "commercial_detail", "redistribution", "avatar_permission",
        "modification", "commercial", "credit_required", "spdx", "license_url", "usage",
    ],
    "additionalProperties": False,
    "properties": {
        "source": {"enum": ["vrm", "declared"]},
        "spec": {"enum": ["vrm0", "vrm1", "none"]},
        # DISPLAY ONLY, never compared (design §11a.9): the card shows the raw word.
        "commercial_detail": {
            "anyOf": [
                {"enum": ["corporation", "personalProfit", "personalNonProfit", "Allow", "Disallow"]},
                {"type": "null"},
            ]
        },
        "redistribution": TRI,
        "avatar_permission": {"enum": ["everyone", "author_only", "named_people", "unknown"]},
        "modification": TRI,
        "commercial": TRI,
        "credit_required": {"type": "boolean"},
        "spdx": {"anyOf": [{"type": "string", "minLength": 1, "maxLength": 64, "pattern": "^[A-Za-z0-9.+() -]+$"}, {"type": "null"}]},
        "license_url": {"$ref": "#/$defs/httpsOrNull"},
        "usage": {
            "type": "object",
            "required": ["violent", "sexual", "political", "antisocial"],
            "additionalProperties": False,
            "properties": {"violent": TRI, "sexual": TRI, "political": TRI, "antisocial": TRI},
        },
    },
}

CREDITS = {
    "type": "array",
    "maxItems": 32,
    "items": {
        "type": "object",
        "required": ["name", "role", "url"],
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "minLength": 1, "maxLength": 128},
            "role": {"type": "string", "maxLength": 64},
            "url": {"$ref": "#/$defs/httpsOrNull"},
        },
    },
}

CONTENT_CONFIRMED = {
    "type": "object",
    "maxProperties": 16,
    "propertyNames": TEXT_ID,
    "additionalProperties": {"type": "integer", "minimum": 1},
}


def part(kinds: list[str]) -> dict:
    return {
        "type": "object",
        "required": ["part_kind", "digest", "size"],
        "additionalProperties": False,
        "properties": {
            "part_kind": {"enum": kinds},
            "digest": {"$ref": "#/$defs/sha256"},
            "size": {"type": "integer", "minimum": 0},
        },
    }


def artefact(media_types: list[str], max_size: int) -> dict:
    return {
        "type": "object",
        "required": ["sha256", "size", "media_type"],
        "additionalProperties": False,
        "properties": {
            "sha256": {"$ref": "#/$defs/sha256"},
            "size": {"type": "integer", "minimum": 1, "maximum": max_size},
            "media_type": {"enum": media_types},
        },
    }


BASE_REQUIRED = ["id", "version", "author", "listing", "thumbnail", "artefact", "review", "min_astra", "published_at"]


def base_props(art: dict) -> dict:
    return {
        "id": {"$ref": "#/$defs/itemId"},
        "version": {"$ref": "#/$defs/semver"},
        "author": {"type": "string", "minLength": 1, "maxLength": 64},
        "listing": LISTING,
        "thumbnail": THUMBNAIL,
        "artefact": art,
        "review": {"enum": ["unchecked", "reviewed"]},
        "min_astra": {"$ref": "#/$defs/semver"},
        "published_at": {"$ref": "#/$defs/unixSeconds"},
    }


CAPABILITY_WORD = {
    "type": "string",
    "pattern": "^([a-z][a-z_]{1,31}|uses_plugin:[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])|on_event:[a-z][a-z0-9_]{0,63})$",
}

ENTRY = {
    "commands": {
        "required": BASE_REQUIRED + ["capabilities", "danger", "platforms", "requires", "parts", "content_confirmed", "licence", "credits"],
        "props": lambda: {
            **base_props(artefact(["application/vnd.astra.command+json"], MIB)),
            "capabilities": {"type": "array", "maxItems": 64, "items": CAPABILITY_WORD},
            "danger": {"enum": ["low", "high", "critical"]},
            "platforms": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"enum": ["windows", "linux", "macos"]}},
            "requires": {
                "type": "array",
                "maxItems": 16,
                "items": {
                    "type": "object",
                    "required": ["kind", "id", "version_req"],
                    "additionalProperties": False,
                    "properties": {
                        "kind": {"const": "plugin"},
                        "id": {"$ref": "#/$defs/itemId"},
                        "version_req": {"$ref": "#/$defs/versionRange"},
                    },
                },
            },
            "parts": {"type": "array", "minItems": 1, "maxItems": 64, "items": part(["command", "art", "audio"])},
            "content_confirmed": CONTENT_CONFIRMED,
            "licence": LICENCE,
            "credits": CREDITS,
        },
    },
    "characters": {
        "required": BASE_REQUIRED + ["format", "requires", "parts", "content_confirmed", "needs", "licence", "credits"],
        "props": lambda: {
            **base_props(artefact(["application/vnd.astra.character+zip"], 64 * MIB)),
            "format": {"const": "astra.character"},
            "requires": {
                "type": "array",
                "minItems": 1,
                "maxItems": 16,
                "items": {
                    "type": "object",
                    "required": ["kind", "id", "version", "digest"],
                    "additionalProperties": False,
                    "properties": {
                        "kind": {"enum": ["model", "animset"]},
                        "id": {"$ref": "#/$defs/itemId"},
                        "version": {"$ref": "#/$defs/semver"},
                        "digest": {"$ref": "#/$defs/sha256"},
                    },
                },
            },
            "parts": {"type": "array", "maxItems": 64, "items": part(["character", "art", "audio"])},
            "content_confirmed": CONTENT_CONFIRMED,
            "needs": {"type": "array", "maxItems": 16, "items": {"type": "string", "pattern": "^[a-z][a-z0-9-]{0,31}$"}},
            "licence": LICENCE,
            "credits": CREDITS,
        },
    },
    "models": {
        "required": BASE_REQUIRED + ["format", "body_kind", "parts", "content_confirmed", "licence", "credits"],
        "props": lambda: {
            **base_props(artefact(["model/gltf-binary", "application/vnd.astra.character+zip"], 64 * MIB)),
            "format": {"enum": ["vrm", "astra.character"]},
            "body_kind": {"enum": ["vrm", "pixel"]},
            "parts": {"type": "array", "minItems": 1, "maxItems": 1, "items": part(["character"])},
            "content_confirmed": CONTENT_CONFIRMED,
            "licence": LICENCE,
            "credits": CREDITS,
        },
    },
    "animsets": {
        "required": BASE_REQUIRED + ["format", "dimension", "parts", "clips", "states", "content_confirmed", "licence", "credits"],
        "props": lambda: {
            **base_props(artefact(["application/vnd.astra.animpack+zip"], 64 * MIB)),
            "format": {"const": "astra.animpack"},
            "dimension": {"enum": ["3d", "2d"]},
            "parts": {"type": "array", "minItems": 1, "maxItems": 1, "items": part(["animations", "art"])},
            "clips": {"type": "integer", "minimum": 1, "maximum": 4096},
            "states": {"type": "array", "maxItems": 64, "items": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,31}$"}},
            "content_confirmed": CONTENT_CONFIRMED,
            "licence": LICENCE,
            "credits": CREDITS,
        },
    },
    "packs": {
        # No min_astra (design §11a.9: members gate themselves), no licence,
        # no parts: a pack carries no copies (design §1 decision 11).
        "required": ["id", "version", "author", "listing", "thumbnail", "members", "review", "published_at"],
        "props": lambda: {
            "id": {"$ref": "#/$defs/itemId"},
            "version": {"$ref": "#/$defs/semver"},
            "author": {"type": "string", "minLength": 1, "maxLength": 64},
            "listing": LISTING,
            "thumbnail": THUMBNAIL,
            "members": {
                "type": "array",
                "minItems": 1,
                "maxItems": 64,
                "items": {
                    "type": "object",
                    "required": ["kind", "id", "version", "digest"],
                    "additionalProperties": False,
                    "properties": {
                        # never "pack": packs cannot contain packs (design §3.3)
                        "kind": {"enum": ["command", "character", "model", "animset", "game-integration"]},
                        "id": {"type": "string", "minLength": 1, "maxLength": 128, "pattern": "^[a-z0-9][a-z0-9./-]*$"},
                        "version": {"$ref": "#/$defs/semver"},
                        "digest": {"$ref": "#/$defs/sha256"},
                    },
                },
            },
            "review": {"enum": ["unchecked", "reviewed"]},
            "published_at": {"$ref": "#/$defs/unixSeconds"},
        },
    },
}

WITHDRAWN_ROW = {
    "type": "object",
    "required": ["id", "versions", "act", "floor_effect", "reason_code", "reason_text", "at"],
    "additionalProperties": False,
    "properties": {
        "id": {"$ref": "#/$defs/itemId"},
        "versions": {"$ref": "#/$defs/versionRange"},
        "act": {"enum": ["security", "rights", "retired"]},
        "floor_effect": {"enum": ["no-offer", "no-update", "disarm"]},
        "reason_code": {
            "enum": [
                "security", "rights-holder", "policy", "author-request",
                "requires-unavailable", "member-withdrawn", "member-retired", "broken",
            ]
        },
        "part": {
            "type": "object",
            "required": ["part_kind", "digest"],
            "additionalProperties": False,
            "properties": {
                "part_kind": {"enum": ["animations", "character", "art", "audio", "command"]},
                "digest": {"$ref": "#/$defs/sha256"},
            },
        },
        "cause": {
            "type": "object",
            "required": ["kind", "id", "version"],
            "additionalProperties": False,
            "properties": {
                "kind": {"enum": ["plugin", "command", "character", "model", "animset", "game-integration"]},
                "id": {"type": "string", "minLength": 1, "maxLength": 128, "pattern": "^[a-z0-9][a-z0-9./-]*$"},
                "version": {"$ref": "#/$defs/semver"},
            },
        },
        "reason_text": {"type": "string", "maxLength": 500},
        "at": {"$ref": "#/$defs/unixSeconds"},
    },
}

LIFT_ROW = {
    "type": "object",
    "required": ["id", "versions", "lifts_at"],
    "additionalProperties": False,
    "properties": {
        "id": {"$ref": "#/$defs/itemId"},
        "versions": {"$ref": "#/$defs/versionRange"},
        "lifts_at": {"$ref": "#/$defs/unixSeconds"},
    },
}


def envelope(title: str, desc: str, signed: dict, defs: dict, fname: str) -> dict:
    d = copy.deepcopy(DEFS_COMMON)
    d.update(defs)
    d["signed"] = signed
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": BASE_ID + fname,
        "title": title,
        "description": desc,
        "type": "object",
        "required": ["signed", "signatures"],
        "additionalProperties": False,
        "properties": {
            "$comment": {"type": "string"},
            "signed": {"$ref": "#/$defs/signed"},
            "signatures": {"type": "array", "maxItems": 4, "items": {"$ref": "#/$defs/signature"}},
        },
        "$defs": d,
    }


def index_schema(kind: str) -> dict:
    e = ENTRY[kind]
    entry = {"type": "object", "required": e["required"], "additionalProperties": False, "properties": e["props"]()}
    signed = {
        "type": "object",
        "required": ["schema", "serial", "issued_at", "expires_at", "entries"],
        "additionalProperties": False,
        "properties": {
            "schema": {"const": f"astra.{kind}.index/1"},
            "serial": {"type": "integer", "minimum": 1},
            "issued_at": {"$ref": "#/$defs/unixSeconds"},
            "expires_at": {"$ref": "#/$defs/unixSeconds"},
            "entries": {"type": "array", "items": {"$ref": "#/$defs/entry"}},
        },
    }
    fname = f"{kind}-index-v1.schema.json"
    return envelope(
        f"astra.{kind}.index/1",
        f"spec/content/{kind}-index-v1.md. GENERATED by tools/gen-content-schemas.py. The envelope is the plugin one "
        "(docs/en/spec/registry-index.md §1); signature, freshness, kind-key scoping and the cross-field rules are "
        "tools/check-content-goldens.py's semantic rules, not this schema's.",
        signed,
        {"entry": entry},
        fname,
    )


def withdrawn_schema(kind: str) -> dict:
    signed = {
        "type": "object",
        "required": ["schema", "serial", "issued_at", "expires_at", "rows", "lifts"],
        "additionalProperties": False,
        "properties": {
            "schema": {"const": f"astra.{kind}.withdrawn/1"},
            "serial": {"type": "integer", "minimum": 1},
            "issued_at": {"$ref": "#/$defs/unixSeconds"},
            "expires_at": {"$ref": "#/$defs/unixSeconds"},
            "rows": {"type": "array", "items": {"$ref": "#/$defs/row"}},
            "lifts": {"type": "array", "items": {"$ref": "#/$defs/lift"}},
        },
    }
    fname = f"{kind}-withdrawn-v1.schema.json"
    return envelope(
        f"astra.{kind}.withdrawn/1",
        f"spec/content/{kind}-withdrawn-v1.md. GENERATED by tools/gen-content-schemas.py. This is what the PUBLISHER "
        "must emit; a client never refuses a whole withdrawn document for an act or reason_code it does not know "
        "(common-v1.md §6.3).",
        signed,
        {"row": WITHDRAWN_ROW, "lift": LIFT_ROW},
        fname,
    )


def kind_keys_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": BASE_ID + "trust-kind-keys-v1.schema.json",
        "title": "astra.registry.trust/1 — the kind_keys member",
        "description": "spec/content/trust-kind-keys-v1.md. GENERATED by tools/gen-content-schemas.py. What the ROOT "
        "ceremony must publish; the client's fail-closed reading of a set that breaks it is §4 of that spec.",
        "type": "array",
        "maxItems": 2 * len(KEY_KINDS),
        "items": {"$ref": "#/$defs/kindKey"},
        "$defs": {
            "kindKey": {
                "type": "object",
                "required": ["kind", "role", "key_id", "alg", "public_key", "not_before"],
                "additionalProperties": False,
                "properties": {
                    "kind": {"enum": KEY_KINDS},
                    "role": {"enum": ["current", "next"]},
                    "key_id": {"type": "string", "pattern": "^astra-(" + "|".join(KEY_KINDS) + ")-[0-9]{4}[a-z]$"},
                    "alg": {"const": "ed25519"},
                    "public_key": {"type": "string", "pattern": "^[A-Za-z0-9+/]{43}=$"},
                    "not_before": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"},
                },
            }
        },
    }


def render(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def all_schemas() -> dict[str, str]:
    out = {}
    for k in KINDS:
        out[f"{k}-index-v1.schema.json"] = render(index_schema(k))
        out[f"{k}-withdrawn-v1.schema.json"] = render(withdrawn_schema(k))
    out["trust-kind-keys-v1.schema.json"] = render(kind_keys_schema())
    return out


def main(argv: list[str]) -> int:
    check = "--check" in argv
    want = all_schemas()
    drift = []
    for name, text in want.items():
        p = OUT / name
        if check:
            if not p.exists() or p.read_text(encoding="utf-8") != text:
                drift.append(name)
        else:
            OUT.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
    extra = sorted(p.name for p in OUT.glob("*.json") if p.name not in want) if OUT.exists() else []
    if check:
        if drift or extra:
            print("gen-content-schemas: DRIFT in " + ", ".join(drift + [f"{e} (not generated)" for e in extra]))
            print("  run: python3 tools/gen-content-schemas.py")
            return 1
        print(f"gen-content-schemas: {len(want)} schema files current.")
        return 0
    print(f"gen-content-schemas: wrote {len(want)} files to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
