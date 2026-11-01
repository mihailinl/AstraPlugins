#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Minice — https://minice.ai
"""Every golden in testdata/content/ is accepted, held or refused exactly as
testdata/content/vectors.json records, with exactly the reason code it
records — derived from the golden's own BYTES by an independent reading of
spec/content/, never copied from the generator.

This is lane L0 of the content catalogue (minice
docs/architecture/2026-11-01-content-catalogue.md §10). The server (L1/L2),
the signer (L4) and the client (L8) pin these goldens by this repository's
SHA; this script is the spec-side proof that each golden says what its name
says. It runs in the `content-spec` CI job and installs nothing.

Checks, each named in vectors.json's "check" field:
  schema     spec/content/schemas/*.json alone (tools/schemalite.py)
  semantic   the schema accepts it and ONE named rule below refuses it —
             and every other rule accepts it, so a golden has one defect
  signature  schema and every rule accept it; verification under the kind's
             keys (trust-kind-keys-v1.md) refuses it at the vector's `now`
  ingest     a command artefact or a bundle, run through the §3 ingest order
             (ingest-v1.md); the FIRST failing step's code is the verdict
  scenario   several documents judged together (a pack or character ingest
             against the served state, a cascade, the client's rules)

Run: python3 tools/check-content-goldens.py
"""

from __future__ import annotations

import datetime
import hashlib
import json
import pathlib
import re
import struct
import sys
import unicodedata
import zlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = ROOT / "spec" / "content"
DATA = ROOT / "testdata" / "content"

sys.path.insert(0, str(ROOT / "tools"))
import contentlite as C  # noqa: E402
import schemalite  # noqa: E402

KINDS = ["commands", "characters", "models", "animsets", "packs"]
KEY_KINDS = KINDS + ["games"]
SINGULAR = {"command": "commands", "character": "characters", "model": "models", "animset": "animsets", "pack": "packs"}
DAY = 86400
MAX_SPAN = 8 * DAY
MAX_AHEAD = DAY
WITHDRAWN_MAX_AGE = 2 * 3600  # trust-kind-keys-v1.md §7.1, a client constant: the last verified FETCH
WITHDRAWN_MAX_DOC_AGE = 26 * 3600  # ... and the document's own issued_at (§7.1, OPEN.md O-20: replay)


class Refusal(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


# ── loading ──────────────────────────────────────────────────────────────

def load_json(rel: str):
    """Every golden is read STRICTLY: a duplicate member name is malformed."""
    return C.strict_loads((DATA / rel).read_bytes())


_SCHEMAS: dict[str, dict] = {}


def schema(name: str) -> dict:
    if name not in _SCHEMAS:
        _SCHEMAS[name] = json.loads((SPEC / "schemas" / name).read_text(encoding="utf-8"))
    return _SCHEMAS[name]


def schema_ok(doc, sch: dict) -> tuple[bool, str]:
    try:
        schemalite.validate(doc, sch)
        return True, ""
    except schemalite.SchemaError as e:
        return False, str(e)


# ── trust: the kind_keys reading (trust-kind-keys-v1.md §4) ──────────────

def rfc3339(s) -> int | None:
    if not isinstance(s, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", s):
        return None
    try:
        return int(datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp())
    except ValueError:
        return None


def kind_keys_for(member: dict, kind: str, now: int) -> list[tuple[str, bytes]]:
    """The keys a client may verify `astra.<kind>.*` with at `now`. Every
    defect in the kind's rows costs the KIND its keys (fail closed), never
    one row; a row of another, unknown kind is ignored except that sharing a
    public key with it still costs this kind its keys."""
    rows = member.get("kind_keys")
    if not isinstance(rows, list):
        return []
    mine = [r for r in rows if isinstance(r, dict) and r.get("kind") == kind]
    if len(mine) != 2 or sorted(str(r.get("role")) for r in mine) != ["current", "next"]:
        return []
    parsed = {}
    for r in mine:
        if r.get("alg") != "ed25519":
            return []
        pk = C.unb64(r.get("public_key", "")) if isinstance(r.get("public_key"), str) else None
        nb = rfc3339(r.get("not_before"))
        if pk is None or len(pk) != 32 or nb is None or not isinstance(r.get("key_id"), str):
            return []
        parsed[r["role"]] = (r["key_id"], pk, nb)
    if not parsed["next"][2] > parsed["current"][2]:
        return []
    mine_pks = {parsed["current"][1], parsed["next"][1]}
    if parsed["current"][1] == parsed["next"][1]:
        return []
    for r in rows:
        if isinstance(r, dict) and r.get("kind") != kind and isinstance(r.get("public_key"), str):
            if C.unb64(r["public_key"]) in mine_pks:
                return []
    for r in member.get("index_keys") or []:
        if isinstance(r, dict) and isinstance(r.get("public_key"), str) and C.unb64(r["public_key"]) in mine_pks:
            return []
    return [(kid, pk) for kid, pk, nb in (parsed["current"], parsed["next"]) if now >= nb]


def verified_by(env: dict, kind: str, doc: str, member: dict, now: int) -> tuple[set[str], str | None]:
    """EVERY usable key of the kind that verifies one of the offered signatures — never
    the first only (F9): a document dual-signed by `current` and `next` retires `current`
    whatever order its signatures are in. The domain is THIS function's constant."""
    keys = kind_keys_for(member, kind, now)
    if not keys:
        return set(), "kind-keys-unusable"
    digest = C.signing_digest(f"astra.{kind}.{doc}/1", env.get("signed"))
    got = set()
    for s in env.get("signatures") or []:
        sig = C.unb64(s.get("sig", "")) if isinstance(s, dict) and isinstance(s.get("sig"), str) else None
        if sig is None:
            continue
        for kid, pk in keys:
            if C.verify(pk, digest, sig):
                got.add(kid)
    return got, (None if got else "signature-invalid")


def verify_doc(env: dict, kind: str, doc: str, member: dict, now: int, retired: set[str] = frozenset()):
    """(a key id that verified and is not retired, None) or (None, reason). When several
    verify, the one reported is the `next` key if it is among them."""
    got, why = verified_by(env, kind, doc, member, now)
    if why:
        return None, why
    live = got - set(retired)
    if not live:
        return None, "key-retired"
    role = {r.get("key_id"): r.get("role") for r in member.get("kind_keys", []) if isinstance(r, dict) and r.get("kind") == kind}
    return sorted(live, key=lambda k: (role.get(k) != "next", k))[0], None


# ── semantic rules over a document (common-v1.md, <kind>-index-v1.md) ───

def rule_expiry_span(s, ctx) -> bool:
    return 0 < s["expires_at"] - s["issued_at"] <= MAX_SPAN


def rule_issued_in_future(s, ctx) -> bool:
    return s["issued_at"] <= ctx["now"] + MAX_AHEAD


def rule_serial_is_issued_at(s, ctx) -> bool:
    return s["serial"] == s["issued_at"]


def _entries(s):
    return s.get("entries", [])


def rule_id_double_hyphen(s, ctx) -> bool:
    return all("--" not in e["id"] for e in _entries(s)) and all("--" not in r["id"] for r in s.get("rows", []))


def rule_unique_id_version(s, ctx) -> bool:
    keys = [(e["id"], e["version"]) for e in _entries(s)]
    return len(keys) == len(set(keys))


def rule_licence_allowed(s, ctx) -> bool:
    """Only an Allowed verdict publishes (design §1 decision 5): a signed
    entry that says otherwise is refused by the client too."""
    for e in _entries(s):
        lic = e.get("licence")
        if lic and (lic["redistribution"] == "prohibited" or lic["avatar_permission"] in ("author_only", "named_people")):
            return False
    return True


def rule_licence_source_spec(s, ctx) -> bool:
    for e in _entries(s):
        lic = e.get("licence")
        if lic and ((lic["source"] == "vrm") != (lic["spec"] in ("vrm0", "vrm1"))):
            return False
    return True


def rule_vrm0_usage(s, ctx) -> bool:
    for e in _entries(s):
        lic = e.get("licence")
        if lic and lic["spec"] == "vrm0" and (lic["usage"]["political"] != "unknown" or lic["usage"]["antisocial"] != "unknown"):
            return False
    return True


def rule_capabilities_sorted(s, ctx) -> bool:
    for e in _entries(s):
        caps = e.get("capabilities")
        if caps is not None and caps != sorted(set(caps)):
            return False
    return True


def rule_parts_confirmed(s, ctx) -> bool:
    return all(not e.get("parts") or e.get("content_confirmed") for e in _entries(s))


def rule_one_command_part(s, ctx) -> bool:
    return all(sum(p["part_kind"] == "command" for p in e["parts"]) == 1 for e in _entries(s))


def rule_requires_match_capabilities(s, ctx) -> bool:
    for e in _entries(s):
        plugins = {c.split(":", 1)[1] for c in e["capabilities"] if c.startswith("uses_plugin:")}
        if plugins != {r["id"] for r in e["requires"]} or len(e["requires"]) != len(plugins):
            return False
    return True


def rule_one_model(s, ctx) -> bool:
    for e in _entries(s):
        keys = [(r["kind"], r["id"]) for r in e["requires"]]
        if len(keys) != len(set(keys)) or sum(r["kind"] == "model" for r in e["requires"]) != 1:
            return False
    return True


def rule_model_format(s, ctx) -> bool:
    for e in _entries(s):
        mt = e["artefact"]["media_type"]
        if e["format"] == "vrm" and (e["body_kind"] != "vrm" or mt != "model/gltf-binary"):
            return False
        if e["format"] == "astra.character" and mt != "application/vnd.astra.character+zip":
            return False
        if e["body_kind"] == "pixel" and e["licence"]["source"] != "declared":
            return False
    return True


def rule_dimension_part(s, ctx) -> bool:
    want = {"3d": "animations", "2d": "art"}
    return all(e["parts"][0]["part_kind"] == want[e["dimension"]] for e in _entries(s))


def rule_unique_members(s, ctx) -> bool:
    for e in _entries(s):
        keys = [(m["kind"], m["id"]) for m in e["members"]]
        if len(keys) != len(set(keys)):
            return False
    return True


CASCADE_REASONS = {"requires-unavailable", "member-withdrawn", "member-retired"}
FLOOR_OF_ACT = {"security": {"disarm"}, "rights": {"disarm"}, "retired": {"no-update", "disarm"}}


def rule_security_pairs(s, ctx) -> bool:
    return all(r["act"] == "security" for r in s["rows"] if r["reason_code"] == "security")


def rule_floor_of_act(s, ctx) -> bool:
    return all(r["floor_effect"] in FLOOR_OF_ACT[r["act"]] for r in s["rows"])


def rule_part_only_rights(s, ctx) -> bool:
    for r in s["rows"]:
        if "part" in r and (r["act"] != "rights" or ctx["kind"] == "packs"):
            return False
    return True


def rule_cause_on_cascade(s, ctx) -> bool:
    return all(("cause" in r) == (r["reason_code"] in CASCADE_REASONS) for r in s["rows"])


def rule_lift_not_contradicted(s, ctx) -> bool:
    sec = {(r["id"], r["versions"], r["at"]) for r in s["rows"] if r["act"] == "security"}
    return all((l["id"], l["versions"], l["lifts_at"]) not in sec for l in s["lifts"])


COMMON_RULES = {
    "expiry-span": rule_expiry_span,
    "issued-in-future": rule_issued_in_future,
    "serial-is-issued-at": rule_serial_is_issued_at,
    "id-double-hyphen": rule_id_double_hyphen,
}
INDEX_RULES = {
    **COMMON_RULES,
    "unique-id-version": rule_unique_id_version,
    "licence-allowed": rule_licence_allowed,
    "licence-source-spec": rule_licence_source_spec,
    "vrm0-usage": rule_vrm0_usage,
    "parts-confirmed": rule_parts_confirmed,
}
KIND_INDEX_RULES = {
    "commands": {"capabilities-sorted": rule_capabilities_sorted, "one-command-part": rule_one_command_part,
                 "requires-match-capabilities": rule_requires_match_capabilities},
    "characters": {"one-model": rule_one_model},
    "models": {"model-format": rule_model_format},
    "animsets": {"dimension-part": rule_dimension_part},
    "packs": {"unique-members": rule_unique_members},
}
WITHDRAWN_RULES = {
    **COMMON_RULES,
    "security-pairs": rule_security_pairs,
    "floor-of-act": rule_floor_of_act,
    "part-only-rights": rule_part_only_rights,
    "cause-on-cascade": rule_cause_on_cascade,
    "lift-not-contradicted": rule_lift_not_contradicted,
}


def rules_for(kind: str, doc: str) -> dict:
    return {**INDEX_RULES, **KIND_INDEX_RULES[kind]} if doc == "index" else WITHDRAWN_RULES


def failing_rules(signed: dict, kind: str, doc: str, now: int) -> list[str]:
    ctx = {"now": now, "kind": kind}
    return [name for name, fn in rules_for(kind, doc).items() if not fn(signed, ctx)]


# ── the command extractor, closed (capabilities-v1.md) ───────────────────

PLUGIN_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])$")
ACTION_CAPS = {
    "code": ["runs_code"], "execute": ["executes_shell"], "system": ["system_control"],
    "kill_process": ["system_control"], "type_text": ["controls_input"], "press_keys": ["controls_input"],
    "mouse_click": ["controls_input"], "macro": ["controls_input"], "ui_click": ["ui_automation"],
    "ui_type": ["ui_automation"], "clipboard": ["accesses_clipboard"], "screenshot": ["takes_screenshots", "uses_ai"],
    "send_to_ai": ["uses_ai"], "ai_request": ["uses_ai"], "stream_to_chat": ["uses_ai"], "work_task": ["uses_ai"],
    "open_url": ["opens_urls"], "open_file": ["file_access"], "open_application": ["file_access", "launches_apps"],
    "play_sound": ["plays_audio"], "control_music": ["plays_audio"], "speak": ["plays_audio"],
    "youtube_play": ["plays_audio"], "set_volume": ["system_control"], "notify": ["sends_notifications"],
    "run_command": ["runs_command"], "companion_animation": ["drives_companion"],
    "set_companion_enabled": ["drives_companion"],
    "condition": [], "loop": [], "set_variable": [], "wait": [], "noop": [],
}
# The serde tags of astra-core `command::action::Action` (Astra origin/main 5d5ae5e83): the ONLY
# types a LINEAR action may carry. `open_file` and `plugin__…` exist only as graph-node action types.
LINEAR_TAGS = {
    "speak", "execute", "open_url", "open_application", "type_text", "press_keys", "mouse_click",
    "set_variable", "wait", "condition", "loop", "send_to_ai", "kill_process", "system", "clipboard",
    "notify", "play_sound", "control_music", "noop", "code", "ai_request", "stream_to_chat", "set_volume",
    "screenshot", "ui_click", "ui_type", "youtube_play", "run_command", "companion_animation",
    "set_companion_enabled", "work_task", "macro", "dynamic",
}
EXECUTE_OPEN_MODE = "open"  # astra-core action.rs: `Execute` with this shell opens a file, it runs nothing
CRITICAL = {"code", "execute", "run_command", "macro"}
HIGH = {"system", "kill_process", "type_text", "press_keys", "mouse_click", "ui_click", "ui_type", "screenshot",
        "open_url", "open_application", "dynamic", "open_file"}
# `sub_workflow` is a NodeType but is REFUSED in v1: it invokes another workflow the extractor
# does not resolve, the run_command laundering shape, and derives no capability (OPEN.md O-12)
NODE_TYPES = {"start", "end", "action", "condition", "loop", "parallel", "merge", "error_handler",
              "trigger", "sticky_note", "switch", "delay"}
KNOWN_EVENTS = {"shutdown", "login", "logout", "wake_word", "timer", "reminder_fired", "calendar_event_due"}
RANK = {"low": 0, "high": 1, "critical": 2}
EXEC_CAPS = {"executes_shell", "runs_code", "runs_command"}
NETWORK_CAPS = {"opens_urls", "uses_ai"}


def plugin_of(handler: str) -> str:
    m = re.fullmatch(r"plugin__(.+?)__(.+)", handler)
    if not m or not PLUGIN_ID.fullmatch(m.group(1)):
        raise Refusal("E_COMMAND_PLUGIN_UNNAMED", handler)
    return m.group(1)


def _action_type(t, caps: set, req: set) -> str:
    """Scans one action TYPE; returns its danger word."""
    if not isinstance(t, str) or t == "":
        raise Refusal("E_COMMAND_UNKNOWN_ACTION", repr(t))
    if t == "dynamic":
        raise Refusal("E_COMMAND_PLUGIN_UNNAMED", "a dynamic action with no plugin id")
    if t.startswith("plugin__"):
        pid = plugin_of(t)
        caps.add(f"uses_plugin:{pid}")
        req.add(pid)
        return "high"
    if t not in ACTION_CAPS:
        raise Refusal("E_COMMAND_UNKNOWN_ACTION", t)
    caps.update(ACTION_CAPS[t])
    return "critical" if t in CRITICAL else "high" if t in HIGH else "low"


def _linear(a, caps, req) -> str:
    if not isinstance(a, dict):
        raise Refusal("E_COMMAND_FORMAT", "an action that is not an object")
    t = a.get("type")
    if t not in LINEAR_TAGS:
        raise Refusal("E_COMMAND_UNKNOWN_ACTION", f"linear {t!r} is not an Action tag")
    if t == "execute" and a.get("shell") == EXECUTE_OPEN_MODE:
        caps.add("file_access")  # scan_action / action_danger: `Execute(e) if e.is_open_mode()`
        return "low"
    if t == "dynamic":
        pid = plugin_of(str(a.get("handler_id", "")))
        caps.add(f"uses_plugin:{pid}")
        req.add(pid)
        return "high"
    d = _action_type(t, caps, req)
    for key in ("if_true", "if_false", "body"):
        for sub in a.get(key, []) if t in ("condition", "loop") else []:
            d = max(d, _linear(sub, caps, req), key=RANK.get)
    return d


def _trigger(kind, data: dict, caps: set, req: set) -> None:
    if kind == "text":
        caps.add("on_phrase")
    elif kind == "hotkey":
        caps.add("binds_hotkey")
    elif kind == "event":
        name = data.get("event_name")
        if name == "startup":
            caps.add("on_startup")
        elif name in KNOWN_EVENTS:
            caps.add(f"on_event:{name}")
        else:
            raise Refusal("E_COMMAND_UNKNOWN_TRIGGER", f"event {name!r}")
    elif kind == "schedule":
        caps.add("on_schedule")
    elif kind == "dynamic" or (isinstance(kind, str) and kind.startswith("plugin__")):
        pid = plugin_of(str(data.get("handler_id", "")) if kind == "dynamic" else kind)
        caps.add(f"uses_plugin:{pid}")
        req.add(pid)
    else:
        raise Refusal("E_COMMAND_UNKNOWN_TRIGGER", repr(kind))


def derive_command(cmd) -> dict:
    """{capabilities, danger, requires, flags} or Refusal."""
    if not isinstance(cmd, dict) or not isinstance(cmd.get("triggers", []), list) or not isinstance(cmd.get("actions", []), list):
        raise Refusal("E_COMMAND_FORMAT")
    caps: set[str] = set()
    req: set[str] = set()
    danger = "low"
    for t in cmd.get("triggers", []):
        if not isinstance(t, dict):
            raise Refusal("E_COMMAND_FORMAT", "a trigger that is not an object")
        _trigger(t.get("type"), t, caps, req)
    for a in cmd.get("actions", []):
        danger = max(danger, _linear(a, caps, req), key=RANK.get)
    wf = cmd.get("workflow")
    if wf is not None:
        for n in (wf.get("nodes") or {}).values():
            nt = n.get("node_type")
            if nt not in NODE_TYPES:
                raise Refusal("E_COMMAND_UNKNOWN_ACTION", f"node type {nt!r}")
            data = n.get("data") or {}
            if nt == "trigger":
                # a node keeps its trigger's settings under data.config (workflow.rs
                # match_trigger_node_event reads config.event_name); a linear Trigger is flat
                cfg = data.get("config") if isinstance(data.get("config"), dict) else {}
                _trigger(data.get("trigger_type"), {**cfg, "handler_id": data.get("handler_id")}, caps, req)
            elif nt == "action":
                named = data.get("action_type")
                embedded = data.get("action", {}).get("type") if isinstance(data.get("action"), dict) else None
                if named is not None and embedded is not None and named != embedded:
                    raise Refusal("E_COMMAND_UNKNOWN_ACTION", f"two spellings {named!r} / {embedded!r}")
                t = named if named is not None else embedded
                if t is not None:
                    danger = max(danger, _action_type(t, caps, req), key=RANK.get)
    flags = ["F_COMMAND_EXEC_AND_NETWORK"] if caps & EXEC_CAPS and caps & NETWORK_CAPS else []
    return {"capabilities": sorted(caps), "danger": danger, "requires": sorted(req), "flags": flags}


def ingest_command(cmd, claim: dict, served_plugins: dict | None = None) -> dict:
    got = derive_command(cmd)
    if got["capabilities"] != sorted(claim["capabilities"]) or got["danger"] != claim["danger"]:
        raise Refusal("E_COMMAND_CAPS_MISMATCH", f"derived {got['capabilities']} {got['danger']}")
    if got["requires"] != sorted(claim["requires"]):
        raise Refusal("E_COMMAND_REQUIRES_MISMATCH", f"derived {got['requires']}")
    if served_plugins is not None:
        for pid in got["requires"]:
            p = served_plugins.get(pid)
            if not p or not [v for v in p["listed"] if v not in p.get("revoked", [])]:
                raise Refusal("E_COMMAND_REQUIRES_UNLISTED", pid)
    return got


# ── archives (ingest-v1.md §3) ───────────────────────────────────────────

MAX_ENTRIES = 4096
MAX_TOTAL = 128 * 1024 * 1024
MAX_RATIO = 100
MAX_NAME = 240
MAX_SEGMENTS = 16
MAX_MANIFEST = 1024 * 1024
STORED_ONLY = (".vrm", ".glb", ".png", ".jpg", ".webp", ".ktx2")
DEVICE = re.compile(r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?$", re.I)


def end_record(b: bytes):
    tail = b[-(22 + 65535):]
    at = tail.rfind(b"PK\x05\x06")
    if at < 0 or at + 22 > len(tail):
        raise Refusal("E_ZIP_END_RECORD", "no end record at the end")
    eocd = len(b) - len(tail) + at
    _, disk, disk_cd, on_disk, total, cd_size, cd_off, clen = struct.unpack("<IHHHHIIH", b[eocd:eocd + 22])
    if eocd + 22 + clen != len(b):
        raise Refusal("E_ZIP_END_RECORD", "the last end record does not end the file")
    if disk or disk_cd or on_disk != total:
        raise Refusal("E_ZIP_END_RECORD", "several disks")
    if total == 0xFFFF or cd_off == 0xFFFFFFFF or cd_size == 0xFFFFFFFF:
        raise Refusal("E_ZIP_END_RECORD", "zip64 is not accepted in v1")
    if total and (cd_off + cd_size != eocd or b[cd_off:cd_off + 4] != b"PK\x01\x02"):
        raise Refusal("E_ZIP_END_RECORD", "the directory is not where the record says")
    return total, cd_off, cd_size


def name_refusal(name: str) -> str | None:
    why = C.path_refusal(name.rstrip("/") if name.endswith("/") else name)
    if why:
        return why
    if len(name.encode("utf-8")) > MAX_NAME:
        return "too long"
    segs = name.rstrip("/").split("/")
    if len(segs) > MAX_SEGMENTS:
        return "too deep"
    for s in segs:
        if s == "." or ":" in s or DEVICE.match(s) or s != s.strip() or s.endswith("."):
            return f"segment {s!r}"
    return None


def walk_zip(b: bytes) -> dict[str, bytes]:
    total, cd_off, cd_size = end_record(b)
    if total > MAX_ENTRIES:
        raise Refusal("E_ARCHIVE_TOO_MANY_ENTRIES", str(total))
    entries = []
    p = cd_off
    for _ in range(total):
        if b[p:p + 4] != b"PK\x01\x02":
            raise Refusal("E_ZIP_HEADERS_INCONSISTENT", "a directory entry that is not one")
        (_, made, need, flags, method, _t, _d, crc, csize, usize, nlen, xlen, clen,
         _dn, _ia, ext, loff) = struct.unpack("<IHHHHHHIIIHHHHHII", b[p:p + 46])
        raw_name = b[p + 46:p + 46 + nlen]
        extra = b[p + 46 + nlen:p + 46 + nlen + xlen]
        p += 46 + nlen + xlen + clen
        # zip64 in any spelling: a sentinel size or offset, or the 0x0001 extra field (central or local)
        if 0xFFFFFFFF in (csize, usize, loff):
            raise Refusal("E_ZIP_END_RECORD", "a zip64 sentinel size or offset")
        lx = b[loff + 30 + int.from_bytes(b[loff + 26:loff + 28], "little"):][:int.from_bytes(b[loff + 28:loff + 30], "little")]
        for blob in (extra, lx):
            q = 0
            while q + 4 <= len(blob):
                hid, hlen = struct.unpack("<HH", blob[q:q + 4])
                if hid == 0x0001:
                    raise Refusal("E_ZIP_END_RECORD", "a zip64 extra field")
                q += 4 + hlen
        if flags & 0x1:
            raise Refusal("E_ARCHIVE_ENCRYPTED", raw_name.decode("utf-8", "replace"))
        if method not in (0, 8):
            raise Refusal("E_ARCHIVE_METHOD", str(method))
        mode = (ext >> 16) & 0o170000
        if (made >> 8) == 3 and mode not in (0, 0o100000, 0o040000):
            raise Refusal("E_ARCHIVE_LINK", raw_name.decode("utf-8", "replace"))
        q = 0
        while q + 4 <= len(extra):
            hid, hlen = struct.unpack("<HH", extra[q:q + 4])
            if hid == 0x7075:
                raise Refusal("E_ZIP_HEADERS_INCONSISTENT", "a Unicode Path extra field")
            q += 4 + hlen
        try:
            name = raw_name.decode("utf-8")
        except UnicodeDecodeError:
            raise Refusal("E_ARCHIVE_NAME_UNSAFE", "not UTF-8") from None
        lh = b[loff:loff + 30]
        if len(lh) < 30 or lh[:4] != b"PK\x03\x04":
            raise Refusal("E_ZIP_HEADERS_INCONSISTENT", f"{name}: no local header")
        _, _v, lflags, lmethod, _lt, _ld, lcrc, lcs, lus, lnl, lxl = struct.unpack("<IHHHHHIIIHH", lh)
        lname = b[loff + 30:loff + 30 + lnl]
        if lname != raw_name or lmethod != method or (lflags & 0x9) != (flags & 0x9):
            raise Refusal("E_ZIP_HEADERS_INCONSISTENT", f"{name}: local and central headers disagree")
        if flags & 0x8 and method == 0:
            raise Refusal("E_ZIP_HEADERS_INCONSISTENT", f"{name}: bit 3 on a Stored entry")
        if (lcrc, lcs, lus) != (crc, csize, usize) and not (flags & 0x8 and (lcrc, lcs, lus) == (0, 0, 0)):
            raise Refusal("E_ZIP_HEADERS_INCONSISTENT", f"{name}: local and central sizes disagree")
        if name.endswith("/") and (csize or usize):
            raise Refusal("E_ZIP_HEADERS_INCONSISTENT", f"{name}: a directory entry that carries data")
        entries.append((name, method, crc, csize, usize, loff + 30 + lnl + lxl, flags, loff))
    # the count must account for the WHOLE directory: entries past it are invisible to a reader that
    # trusts the count and visible to one that walks the directory (ingest-v1.md §3 step 1)
    if p != cd_off + cd_size:
        raise Refusal("E_ZIP_HEADERS_INCONSISTENT", "the directory holds more than the end record counts")
    # the entries TILE the file: the first local header at 0, each entry's data (and descriptor)
    # followed at once by the next header, the last one ending where the directory starts. A gap
    # can hide a cloaked entry; an overlap is a second reading of the same bytes (ingest-v1.md §3 step 3)
    at = 0
    crc_of = {e[0]: e[2] for e in entries}
    size_of = {e[0]: e[4] for e in entries}
    for name, _m, _c, csize, _u, data_off, flags, loff in sorted(entries, key=lambda e: e[7]):
        if loff != at:
            raise Refusal("E_ZIP_HEADERS_INCONSISTENT", f"{name}: {'a gap' if loff > at else 'an overlap'} before it")
        at = data_off + csize
        if flags & 0x8:
            # the descriptor sits EXACTLY at the data's end, its signature optional, and says what the
            # central record says; either reading of an ambiguous first word may match, never neither
            want = struct.pack("<III", crc_of[name], csize, size_of[name])
            if b[at:at + 16] == b"PK\x07\x08" + want:
                at += 16
            elif b[at:at + 12] == want:
                at += 12
            else:
                raise Refusal("E_ZIP_HEADERS_INCONSISTENT", f"{name}: the data descriptor disagrees with the directory")
    if at != cd_off:
        raise Refusal("E_ZIP_HEADERS_INCONSISTENT", "bytes between the last entry and the directory")
    # directory order IS file order, so the manifest "last" in the directory is last in the file too
    if [e[7] for e in entries] != sorted(e[7] for e in entries):
        raise Refusal("E_ZIP_HEADERS_INCONSISTENT", "the directory's order is not the file's order")
    folded = set()
    for name, *_ in entries:
        why = name_refusal(name)
        if why:
            raise Refusal("E_ARCHIVE_NAME_UNSAFE", f"{name!r}: {why}")
        key = name.lower()
        if key in folded:
            raise Refusal("E_ARCHIVE_NAME_UNSAFE", f"{name!r}: collides under case folding")
        folded.add(key)
    if sum(e[4] for e in entries) > MAX_TOTAL:
        raise Refusal("E_ARCHIVE_TOO_LARGE", "uncompressed total")
    for name, method, _crc, csize, usize, *_ in entries:
        if method == 8 and usize > MAX_RATIO * max(csize, 1):
            raise Refusal("E_ARCHIVE_RATIO", name)
    for name, method, *_ in entries:
        if method != 0 and name.lower().endswith(STORED_ONLY):
            raise Refusal("E_ARCHIVE_MUST_BE_STORED", name)
    files: dict[str, bytes] = {}
    for name, method, crc, csize, usize, off, flags, _loff in entries:
        if name.endswith("/"):
            continue
        comp = b[off:off + csize]
        if method == 0:
            data = comp
        else:
            d = zlib.decompressobj(-15)
            data = d.decompress(comp, MAX_TOTAL + 1)
            while not d.eof and d.unconsumed_tail == b"" and len(data) <= usize:
                more = d.flush()
                if not more:
                    break
                data += more
            if not d.eof or d.unused_data or d.unconsumed_tail:
                raise Refusal("E_ZIP_HEADERS_INCONSISTENT", f"{name}: the deflate stream does not end at its size")
        if len(data) != usize or (zlib.crc32(data) & 0xFFFFFFFF) != crc:
            raise Refusal("E_ZIP_HEADERS_INCONSISTENT", f"{name}: size or CRC")
        files[name] = data
    files["\0order"] = json.dumps([e[0] for e in entries]).encode()
    return files


def glb_json(raw: bytes):
    if len(raw) < 20 or raw[:4] != b"glTF" or raw[16:20] != b"JSON":
        return None
    n = int.from_bytes(raw[12:16], "little")
    try:
        return C.strict_loads(raw[20:20 + n])
    except C.DuplicateMember:
        return "duplicate"
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


# astra-companion src/vrm/meta.rs at origin/main 045b0bf (`licence_of`, `redistribution_of`), each
# spec's own defaults; plus the design's avatar-permission refusal (§3.3). An UNRECOGNISED token is
# never Allowed: it is Unknown, which holds the version for a moderator (ingest-v1.md §4.2, F3).
AVATAR = {
    "0.x": {"Everyone": "allowed", "OnlyAuthor": "prohibited", "ExplicitlyLicensedPerson": "prohibited"},
    "1.0": {"everyone": "allowed", "onlyAuthor": "prohibited", "onlySeparatelyLicensedPerson": "prohibited"},
}
AVATAR_DEFAULT = {"0.x": "OnlyAuthor", "1.0": "onlyAuthor"}


def _redistribution0(m: dict) -> str:
    ln = m.get("licenseName")
    if not isinstance(ln, str) or ln == "Redistribution_Prohibited":
        return "prohibited"  # absent (or not a string): UniVRM's default
    if ln == "CC0" or ln.startswith("CC_"):
        return "allowed"
    return "unknown"  # "Other" and any other token: the terms are elsewhere


def _redistribution1(m: dict) -> str:
    return "allowed" if m.get("allowRedistribution") is True else "prohibited"  # false, absent, not a bool


def _avatar(spec: str, m: dict) -> str:
    key = "allowedUserName" if spec == "0.x" else "avatarPermission"
    v = m.get(key)
    v = v if isinstance(v, str) else AVATAR_DEFAULT[spec]  # meta.rs `s_or`: absent → the spec default
    return AVATAR[spec].get(v, "unknown")


def meta_verdict(spec: str, m: dict) -> str:
    parts = [_redistribution0(m) if spec == "0.x" else _redistribution1(m), _avatar(spec, m)]
    return "prohibited" if "prohibited" in parts else "unknown" if "unknown" in parts else "allowed"


GLB_MAGIC = b"glTF"
GLB_EXTS = (".vrm", ".glb", ".vrma")
BODY_EXT = ".vrm"  # the names a GLB container may carry (ingest-v1.md §3 step 10)


def gltf_json(raw: bytes):
    """A text `.gltf`: the whole file is the glTF JSON."""
    try:
        return C.strict_loads(raw)
    except C.DuplicateMember:
        return "duplicate"
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def name_matches_magic(p: str, b: bytes) -> bool:
    return (b[:4] == GLB_MAGIC) == p.lower().endswith(GLB_EXTS)


def judged(p: str, b: bytes) -> bool:
    """The verdict runs on CONTENT, never on a name: every GLB by its magic, every `.gltf`."""
    return b[:4] == GLB_MAGIC or p.lower().endswith(".gltf")


def vrm_verdict(raw: bytes, path: str = "") -> str:
    """allowed | prohibited | unknown | conflict — over BOTH metas when a
    file carries both (ingest-v1.md §4.2), never the first one found."""
    g = glb_json(raw) if raw[:4] == GLB_MAGIC else gltf_json(raw)
    if g == "duplicate":
        return "duplicate"
    exts = g.get("extensions") if isinstance(g, dict) else None
    if not isinstance(exts, dict):
        return "unknown"
    verdicts = []
    v0, v1 = exts.get("VRM"), exts.get("VRMC_vrm")
    if isinstance(v0, dict) and isinstance(v0.get("meta"), dict):
        verdicts.append(meta_verdict("0.x", v0["meta"]))
    if isinstance(v1, dict) and isinstance(v1.get("meta"), dict):
        verdicts.append(meta_verdict("1.0", v1["meta"]))
    if not verdicts:
        return "unknown"
    if len(set(verdicts)) > 1:
        return "conflict"
    return verdicts[0]


def is_vrm_body(raw: bytes) -> bool:
    g = glb_json(raw)
    if g == "duplicate":
        return False
    exts = g.get("extensions") if isinstance(g, dict) else None
    return isinstance(exts, dict) and ("VRM" in exts or "VRMC_vrm" in exts)


def parts_of(files: dict[str, bytes], body: str | None, settings_dir: str | None = None):
    """ingest-v1.md §5: the body, each animpacks/<id>/, each accessories/<id>/,
    each standalone image (art) and audio file (audio). Every other file is
    refused, except the character's SETTINGS: a `.toml` directly in its
    `character.dir`, which is configuration, not content."""
    parts: dict[tuple[str, str], dict[str, bytes]] = {}
    for p, b in files.items():
        if p == "astrachar.json" or p.startswith("\0"):
            continue
        segs = p.split("/")
        if settings_dir and p.rsplit("/", 1)[0] == settings_dir.rstrip("/") and p.endswith(".toml"):
            continue
        if body and p == body:
            parts.setdefault(("character", p), {})[p] = b
        elif segs[0] == "animpacks" and len(segs) > 2:
            parts.setdefault(("animations", "/".join(segs[:2])), {})[p] = b
        elif "accessories" in segs[:-2]:
            i = segs.index("accessories")
            parts.setdefault(("character", "/".join(segs[:i + 2])), {})[p] = b
        elif p.lower().endswith((".png", ".jpg", ".webp", ".ktx2")):
            parts.setdefault(("art", p), {})[p] = b
        elif p.lower().endswith((".ogg", ".wav", ".mp3", ".flac")):
            parts.setdefault(("audio", p), {})[p] = b
        else:
            raise Refusal("E_CONTENT_FILE_OUTSIDE_PARTS", p)
    return parts


def ingest_bundle(raw: bytes, ctx: dict) -> dict:
    files = walk_zip(raw)
    order = json.loads(files.pop("\0order"))
    if not order or order[-1] != "astrachar.json":
        raise Refusal("E_BUNDLE_MANIFEST", "astrachar.json is not the last entry")
    man_raw = files["astrachar.json"]
    if len(man_raw) > MAX_MANIFEST:
        raise Refusal("E_BUNDLE_MANIFEST", "too large")
    try:
        man = C.strict_loads(man_raw)
    except (UnicodeDecodeError, json.JSONDecodeError, C.DuplicateMember):
        raise Refusal("E_BUNDLE_MANIFEST", "does not parse") from None
    if man.get("format") not in ("astra.character", "astra.animpack") or man.get("format_version") != 1 or man.get("schema") != 5:
        raise Refusal("E_BUNDLE_MANIFEST", "format, format_version or schema")
    listed = man.get("files") or {}
    for p, b in files.items():
        if p == "astrachar.json":
            continue
        if p not in listed:
            raise Refusal("E_BUNDLE_FILE_UNLISTED", p)
        if listed[p].get("sha256") != "sha256:" + hashlib.sha256(b).hexdigest() or listed[p].get("size") != len(b):
            raise Refusal("E_BUNDLE_FILE_DIGEST", p)
    for p in listed:
        if p not in files:
            raise Refusal("E_BUNDLE_FILE_UNLISTED", f"{p} listed and absent")
    blocked = set(ctx.get("blocklist", []))
    for p, b in files.items():
        if hashlib.sha256(b).hexdigest() in blocked:
            raise Refusal("E_CONTENT_BLOCKED", p)
    body = (man.get("body") or {}).get("file")
    for p, b in files.items():
        if not name_matches_magic(p, b):
            raise Refusal("E_CONTENT_FORMAT", f"{p}: a GLB container's name and magic disagree")
    if body is not None:
        if not body.lower().endswith(BODY_EXT) or body not in files or not is_vrm_body(files[body]):
            raise Refusal("E_CONTENT_FORMAT", f"{body}: not a VRM")
        if len(files[body]) > 50 * 1024 * 1024:
            raise Refusal("E_CONTENT_TOO_LARGE", body)
    verdicts = {p: vrm_verdict(b, p) for p, b in files.items() if judged(p, b)}
    for p, v in verdicts.items():
        if v == "duplicate":
            raise Refusal("E_CONTENT_FORMAT", f"{p}: a duplicate member name in its glTF JSON")
    for want in ("conflict", "prohibited"):
        for p, v in verdicts.items():
            if v == want:
                raise Refusal("E_CONTENT_LICENCE_CONFLICT" if want == "conflict" else "E_CONTENT_LICENCE_REFUSED", p)
    parts = parts_of(files, body, (man.get("character") or {}).get("dir"))
    declared = set(ctx.get("declared_licence", []))
    flags = []
    for (pk, root), pf in sorted(parts.items()):
        has_meta = any(verdicts.get(p) == "allowed" for p in pf)
        if not has_meta and root not in declared:
            unknown = any(verdicts.get(p) == "unknown" for p in pf)
            if not unknown:
                raise Refusal("E_CONTENT_LICENCE_UNDECLARED", root)
    if any(v == "unknown" for v in verdicts.values()):
        flags.append("F_CONTENT_VRM_META_UNKNOWN")
    return {"verdict": "held" if flags else "accept", "flags": flags,
            "parts": {f"{pk}:{root}": C.part_digest(pf) for (pk, root), pf in parts.items()}}


# ── scenarios ────────────────────────────────────────────────────────────

_IDENT = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-(" + _IDENT + r"(?:\." + _IDENT + r")*))?")


def semver_key(v: str):
    """SemVer 2.0.0 §11 precedence as a sort key: major, minor, patch numerically; a version
    WITH a pre-release sorts below the same version without one; pre-release identifiers
    compare left to right, numeric ones numerically and below alphanumeric ones, which compare
    in ASCII order; a longer list of equal leading identifiers sorts higher."""
    m = SEMVER.fullmatch(v)
    if m is None:
        raise ValueError(f"not semver: {v!r}")
    core = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if m.group(4) is None:
        return core, (1,)
    ids = tuple((0, int(i), "") if i.isdigit() else (1, 0, i) for i in m.group(4).split("."))
    return core, (0, ids)


def parse_range(rng: str) -> list[tuple[str, tuple]]:
    """EVERY comparator is parsed before ANY is evaluated (F17): a range with one unparseable
    comparator is unparseable whatever its order, never "false at the first comparator"."""
    if not rng.strip():
        raise ValueError("empty range")
    out = []
    for part in rng.split(","):
        m = re.fullmatch(r"\s*(<=|>=|<|>|=)?\s*(\S+)\s*", part)
        if m is None:
            raise ValueError(part)
        out.append((m.group(1) or "=", semver_key(m.group(2))))
    return out


def in_range(version: str, rng: str) -> bool:
    """Comparators only, SemVer §11 precedence (common-v1.md §6); all must hold."""
    cmps = parse_range(rng)
    x = semver_key(version)
    return all({"<=": x <= v, ">=": x >= v, "<": x < v, ">": x > v, "=": x == v}[op] for op, v in cmps)


def served(kind: str, sc: dict, now: int, member: dict):
    """(entries by (id, version), withdrawn rows) of the SERVED documents of
    `kind`, each verified under its kind's keys first."""
    s = sc["served"].get(kind)
    if not s:
        return None, []
    idx = load_json(s["index"])
    kid, why = verify_doc(idx, kind, "index", member, now)
    if kid is None:
        raise Refusal("E_SERVED_UNVERIFIED", f"{kind} index: {why}")
    rows = []
    if s.get("withdrawn"):
        w = load_json(s["withdrawn"])
        kid, why = verify_doc(w, kind, "withdrawn", member, now)
        if kid is None:
            raise Refusal("E_SERVED_UNVERIFIED", f"{kind} withdrawn: {why}")
        rows = w["signed"]["rows"]
    return {(e["id"], e["version"]): e for e in idx["signed"]["entries"]}, rows


def covers(version: str, rng: str) -> bool:
    """A client's reading of a row's range: one it cannot parse covers EVERY
    version (common-v1.md §6.3) — a takedown must not fail open on syntax."""
    try:
        return in_range(version, rng)
    except (AttributeError, ValueError, KeyError):
        return True


def withdrawn_by(rows, item_id, version):
    acts = [r for r in rows if r["id"] == item_id and covers(version, r["versions"])]
    order = {"security": 2, "rights": 1, "retired": 0}
    return max(acts, key=lambda r: order.get(r["act"], 2)) if acts else None


def scenario_ingest_refs(sc: dict, now: int, member: dict, what: str):
    refs = sc["declared"]
    if what == "pack" and len(refs) > 64:
        raise Refusal("E_PACK_TOO_MANY_MEMBERS")
    prefix = "E_PACK_MEMBER" if what == "pack" else "E_CHARACTER_REQUIRES"
    for r in refs:
        if what == "pack" and r["kind"] == "pack":
            raise Refusal("E_PACK_NESTED", r["id"])
        if what == "pack" and r["kind"] == "game-integration" and not sc.get("games_served"):
            raise Refusal("E_PACK_MEMBER_KIND_UNSERVED", r["id"])
        entries, rows = served(SINGULAR[r["kind"]], sc, now, member)
        e = (entries or {}).get((r["id"], r["version"]))
        if e is None or withdrawn_by(rows, r["id"], r["version"]):
            raise Refusal(f"{prefix}_UNLISTED", r["id"])
        want = e["artefact"]["sha256"] if what == "pack" else e["parts"][0]["digest"]
        if r["digest"] != want:
            raise Refusal(f"{prefix}_DIGEST", r["id"])
    return "accept"


def scenario_cascade(sc: dict, now: int, member: dict):
    """Every listed dependant of a withdrawn member carries its own cascade
    row in its kind's withdrawn document (design §4 table, §11a.10)."""
    dep_kind = sc["dependants"]
    entries, dep_rows = served(dep_kind, sc, now, member)
    for (did, dver), e in entries.items():
        refs = e.get("members") or e.get("requires") or []
        for r in refs:
            if r.get("kind") == "plugin":
                continue
            _, rows = served(SINGULAR[r["kind"]], sc, now, member)
            w = withdrawn_by(rows, r["id"], r["version"])
            if not w:
                continue
            want_act = "security" if w["act"] == "security" else "retired"
            have = [x for x in dep_rows if x["id"] == did and in_range(dver, x["versions"])
                    and x.get("cause", {}).get("id") == r["id"]
                    and (x["act"] == want_act or x["act"] == "security")]
            if not have:
                raise Refusal("cascade-missing", f"{did} needs a {want_act} row caused by {r['id']}")
    return "accept"


def scenario_requires_digest(sc: dict, now: int, member: dict):
    chars, _ = served("characters", sc, now, member)
    for e in chars.values():
        for r in e["requires"]:
            got, rows = served(SINGULAR[r["kind"]], sc, now, member)
            target = (got or {}).get((r["id"], r["version"]))
            if target is None or withdrawn_by(rows, r["id"], r["version"]):
                raise Refusal("requires-unavailable", r["id"])
            if target["parts"][0]["digest"] != r["digest"]:
                raise Refusal("requires-digest-mismatch", r["id"])
    return "accept"


def scenario_sticky(sc: dict, now: int, member: dict):
    """trust-kind-keys-v1.md §7.2: a security row is sticky until a lift
    names its id, its versions and its `at`."""
    sticky: set = set()
    states = []
    floor = 0
    for f in sc["sequence"]:
        env = load_json(f)
        kid, why = verify_doc(env, sc["kind"], "withdrawn", member, now)
        if kid is None or env["signed"]["serial"] < floor:
            states.append("unverified")
            continue
        floor = env["signed"]["serial"]
        for r in env["signed"]["rows"]:
            # an unknown act whose floor is disarm is sticky the same way (trust-kind-keys-v1.md §7.2)
            if r.get("act") == "security" or (r.get("act") not in ("rights", "retired") and client_effect(r) == "disarm"):
                sticky.add((r["id"], r["versions"], r["at"]))
        for lift in env["signed"]["lifts"]:
            sticky.discard((lift["id"], lift["versions"], lift["lifts_at"]))
        inst = sc["installed"]
        states.append("disarmed" if any(i == inst["id"] and covers(inst["version"], v) for i, v, _ in sticky) else "armed")
    return states


def client_effect(row: dict) -> str:
    """common-v1.md §6.3: a known act decides; an unknown one falls back to
    floor_effect; an unknown floor_effect is the strongest, disarm."""
    act = {"security": "disarm", "rights": "disarm", "retired": "no-update"}.get(row.get("act"))
    if act:
        return act
    return row.get("floor_effect") if row.get("floor_effect") in ("no-offer", "no-update", "disarm") else "disarm"


def withdrawn_fresh(age: int, latest_verified: bool, doc_age: int = 0) -> bool:
    return latest_verified and 0 <= age <= WITHDRAWN_MAX_AGE and doc_age <= WITHDRAWN_MAX_DOC_AGE


def serial_accept(floor: int, floor_bytes: str | None, serial: int, bytes_: str) -> bool:
    if serial < floor:
        return False
    return not (serial == floor and floor_bytes is not None and floor_bytes != bytes_)


# ── reason codes (spec/content/reason-codes.yaml) ────────────────────────

def load_codes() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    section = None
    for line in (SPEC / "reason-codes.yaml").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([a-z_]+):\s*$", line)
        if m:
            section = m.group(1)
            out[section] = {}
            continue
        m = re.match(r"^  ([A-Za-z0-9_:-]+):\s*(\S+)\s*$", line)
        if m and section:
            out[section][m.group(1)] = m.group(2)
            continue
        raise ValueError(f"reason-codes.yaml: unparseable line {line!r}")
    return out


# ── the runner ───────────────────────────────────────────────────────────

def main() -> int:
    V = load_json("vectors.json")
    now0 = V["now"]
    failures: list[str] = []
    checked = 0

    def report(name, ok, detail=""):
        nonlocal checked
        checked += 1
        print(("ok   " if ok else "FAIL ") + name + (f" — {detail}" if detail and not ok else ""))
        if not ok:
            failures.append(name)

    # -- SHA256SUMS: every generated byte is what was recorded --------------
    sums = {}
    for line in (DATA / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        h, p = line.split("  ", 1)
        sums[p] = h
    bad = [p for p, h in sums.items() if not (DATA / p).is_file() or hashlib.sha256((DATA / p).read_bytes()).hexdigest() != h]
    report(f"SHA256SUMS ({len(sums)} files)", not bad, ", ".join(bad[:5]))

    # -- trust ------------------------------------------------------------
    T = V["trust"]
    trust = load_json(T["file"])
    root_pk = C.unb64(T["root_public_key"])
    ok_root = any(C.verify(root_pk, C.signing_digest("astra.registry.trust/1", trust["signed"]), C.unb64(s["sig"]) or b"")
                  for s in trust["signatures"])
    report("trust/trust.json verifies under the TEST root as astra.registry.trust/1", ok_root)
    report("trust/trust.json does NOT verify as astra.commands.index/1 (domain)",
           not any(C.verify(root_pk, C.signing_digest("astra.commands.index/1", trust["signed"]), C.unb64(s["sig"]) or b"")
                   for s in trust["signatures"]))
    member = trust["signed"]
    kk_schema = schema("trust-kind-keys-v1.schema.json")
    sok, d = schema_ok(member["kind_keys"], kk_schema)
    report("trust/trust.json kind_keys (schema)", sok, d)
    for v in T["kind_keys"]:
        doc = load_json(v["file"])
        sok, d = schema_ok(doc["kind_keys"], kk_schema)
        report(f"trust/kind-keys/{v['name']} (publisher schema)", sok == (v["schema_verdict"] == "accept"), d)
        for when, expect in v["expect"].items():
            now = int(when) if when != "now" else now0
            got = {k: [kid for kid, _ in kind_keys_for(doc, k, now)] for k in KEY_KINDS}
            report(f"trust/kind-keys/{v['name']} @ {when}", got == expect, f"got {got}")

    # -- part digest --------------------------------------------------------
    for v in V["part_digest"]:
        base = DATA / v["dir"]
        files = {p.relative_to(base).as_posix(): p.read_bytes() for p in sorted(base.rglob("*")) if p.is_file()}
        files = {unicodedata.normalize("NFC", k): b for k, b in files.items()}
        jcs = C.jcs(C.part_digest_pairs(files))
        report(f"part-digest/{v['name']} JCS bytes", jcs == (DATA / v["jcs"]).read_bytes())
        report(f"part-digest/{v['name']} = {v['part_digest'][:8]}…", C.part_digest(files) == v["part_digest"])
    for v in V["part_digest_refusals"]:
        report(f"part-digest refuses {v['name']}", C.path_refusal(v["path"]) == v["rule"], str(C.path_refusal(v["path"])))

    # -- index and withdrawn documents --------------------------------------
    cmd_by_sha = {}
    for p in sorted((DATA / "commands").rglob("*.command.json")):
        cmd_by_sha[hashlib.sha256(p.read_bytes()).hexdigest()] = json.loads(p.read_text(encoding="utf-8"))
    for section, doc in (("index", "index"), ("withdrawn", "withdrawn")):
        for v in V[section]:
            kind = v["kind"]
            label = f"{section}/{kind}/{v['name']}"
            try:
                env = load_json(v["file"])
            except C.DuplicateMember as dm:
                report(label, v.get("check") == "parse", f"a duplicate member name {dm}")
                continue
            if v.get("check") == "parse":
                report(label, False, "parsed, and must not")
                continue
            now = v.get("now", now0)
            sok, d = schema_ok(env, schema(f"{kind}-{doc}-v1.schema.json"))
            fails = failing_rules(env["signed"], kind, doc, now) if sok else ["(schema)"]
            kid, why = verify_doc(env, kind, doc, member, now) if sok else (None, "schema")
            if v["verdict"] == "accept":
                report(label, sok and not fails and kid is not None, f"schema={sok} {d} rules={fails} sig={why}")
                if kid is not None and v.get("signed_by"):
                    report(f"{label} verified by {v['signed_by']}", kid == v["signed_by"], kid)
                if v.get("verified_by"):
                    ids, _ = verified_by(env, kind, doc, member, now)
                    report(f"{label} verified by every one of {v['verified_by']}", sorted(ids) == v["verified_by"], str(sorted(ids)))
            elif v["check"] == "schema":
                report(label, sok is False, "the schema accepted it")
            elif v["check"] == "semantic":
                report(label, sok and fails == [v["rule"]], f"schema={sok} {d} failing={fails}")
            elif v["check"] == "signature":
                report(label, sok and not fails and kid is None and why == v["reason"], f"rules={fails} sig={kid}/{why}")
            else:
                raise NotImplementedError(v["check"])
            # the client shows what IT derives; an index claim that differs is claim-mismatch (capabilities-v1.md §6)
            if kind == "commands" and doc == "index" and v["verdict"] == "accept":
                for e in env["signed"]["entries"]:
                    art = cmd_by_sha.get(e["artefact"]["sha256"])
                    try:
                        got = derive_command(art) if art is not None else None
                    except Refusal as r:
                        got = {"refused": r.code}
                    want = {"capabilities": e["capabilities"], "danger": e["danger"],
                            "requires": sorted(r["id"] for r in e["requires"])}
                    report(f"{label}: {e['id']} claim == client derivation",
                           got is not None and {k: got.get(k) for k in want} == want, f"got {got}")

    # -- commands (ingest) ----------------------------------------------------
    for v in V["commands"]:
        try:
            cmd = load_json(v["file"])
            got = ingest_command(cmd, v["claim"], v.get("served_plugins"))
            outcome, flags = "accept", got["flags"]
        except Refusal as r:
            outcome, flags = r.code, []
        except (C.DuplicateMember, json.JSONDecodeError):
            outcome, flags = "E_COMMAND_FORMAT", []
        want = v["verdict"] if v["verdict"] == "accept" else v["code"]
        report(f"commands/{v['name']}", outcome == want and flags == v.get("flags", []),
               f"got {outcome} flags={flags}")

    # -- archives (ingest) -------------------------------------------------
    for v in V["archives"]:
        raw = (DATA / v["file"]).read_bytes()
        try:
            got = ingest_bundle(raw, v)
            outcome, flags, parts = got["verdict"], got["flags"], got["parts"]
        except Refusal as r:
            outcome, flags, parts = r.code, [], {}
        want = v["verdict"] if v["verdict"] in ("accept", "held") else v["code"]
        report(f"archives/{v['name']}", outcome == want and flags == v.get("flags", []), f"got {outcome} flags={flags}")
        for pk, digest in v.get("parts", {}).items():
            report(f"archives/{v['name']} part {pk}", parts.get(pk) == digest, f"got {parts.get(pk)}")

    # -- scenarios -----------------------------------------------------------
    for v in V["scenarios"]:
        now = v.get("now", now0)
        t = v["type"]
        label = f"scenario/{v['name']}"
        try:
            if t == "pack-ingest":
                got = scenario_ingest_refs(v, now, member, "pack")
            elif t == "character-ingest":
                got = scenario_ingest_refs(v, now, member, "character")
            elif t == "cascade":
                got = scenario_cascade(v, now, member)
            elif t == "requires-digest":
                got = scenario_requires_digest(v, now, member)
            elif t == "sticky":
                got = scenario_sticky(v, now, member)
            elif t == "one-way-switch":
                # trust-kind-keys-v1.md §6: verifying under K's `next` retires K's `current` KEY ID
                role = {r["key_id"]: r["role"] for r in member["kind_keys"] if r.get("kind") == v["kind"]}
                retired: set[str] = set()
                got = []
                for f in v["sequence"]:
                    env = load_json(f)
                    kid, why = verify_doc(env, v["kind"], "index", member, now, retired)
                    got.append(kid or why)
                    ids, _ = verified_by(env, v["kind"], "index", member, now)
                    if kid and any(role.get(k) == "next" for k in ids):
                        retired |= {k for k, r in role.items() if r == "current"}
            elif t == "client-floor":
                env = load_json(v["file"])
                got = [client_effect(r) for r in env["signed"]["rows"]]
            elif t == "withdrawn-freshness":
                got = ["allow" if withdrawn_fresh(c["age"], c["latest_verified"], c.get("doc_age", 0)) else "refuse"
                       for c in v["cases"]]
            elif t == "client-covers":
                got = [covers(c["version"], c["versions"]) for c in v["cases"]]
            elif t == "serial-floor":
                got = ["accept" if serial_accept(c["floor"], c.get("floor_bytes"), c["serial"], c["bytes"]) else "refuse"
                       for c in v["cases"]]
            else:
                raise NotImplementedError(t)
        except Refusal as r:
            got = r.code
        report(label, got == v["expect"], f"got {got}")

    # -- reason codes, both directions (reason-codes.yaml) ------------------
    codes = load_codes()
    every = {c for sec in codes.values() for c in sec}
    spec_text = "\n".join(p.read_text(encoding="utf-8") for p in sorted(SPEC.glob("*.md")))
    cited = set(re.findall(r"\b[EF]_[A-Z][A-Z0-9_]+\b", spec_text))
    report("every E_/F_ code the specs cite is in reason-codes.yaml", cited <= every, str(sorted(cited - every)))
    missing = [c for sec in ("ingest", "flags") for c in codes.get(sec, {}) if c not in spec_text]
    report("every ingest code and flag in reason-codes.yaml is specified in a spec/content/*.md", not missing, str(missing))
    used = {v.get("code") for v in V["commands"] + V["archives"] if v.get("code")}
    used |= {f for v in V["commands"] + V["archives"] for f in v.get("flags", [])}
    used |= {v["expect"] for v in V["scenarios"] if isinstance(v["expect"], str) and v["expect"] != "accept"}
    report("every code vectors.json expects is in reason-codes.yaml", used <= every, str(sorted(used - every)))
    client_codes = set(codes.get("client", {}))
    report("every client token is specified in a spec/content/*.md",
           all(f"`{c}`" in spec_text for c in client_codes), str([c for c in client_codes if f"`{c}`" not in spec_text]))

    print(f"\n{checked} checks, {len(failures)} failed.")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("check-content-goldens: all checks pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
