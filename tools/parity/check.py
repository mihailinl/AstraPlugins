#!/usr/bin/env python3
"""Fail the build when `spec/hooks.yaml`, the proto, and the SDK sources disagree.

    python3 tools/parity/check.py            # all rules
    python3 tools/parity/check.py --rules R1,R4
    python3 tools/parity/check.py --astra-dir /path/to/Astra/astra-rs
    python3 tools/parity/check.py --fix-provenance   # re-point moved daemon_calls lines

Rules:
  R1  a hook is `stable` in the spec but the SDK has no binding for it
      (R1b: a hook is `n/a` in the spec but the SDK binds it after all)
  R2  an SDK binds an rpc that has no row in the spec
  R3  an rpc exists in the proto's plugin-facing services but in no spec row
      (R3b: a spec row names an rpc the proto does not declare;
       R3c: a row's `streaming` kind disagrees with the proto)
  R4  a `planned` row is past its `grace_until`
  R5  `daemon_calls` does not point at the call site it claims. Needs an Astra
      checkout ($ASTRA_RS_DIR, else ../Astra/astra-rs); skipped, loudly, without one.
  R6  a PluginHostService row's `permission` disagrees with the daemon's
      HOST_RPC_PERMISSIONS — the table `require_permission` reads. Same checkout,
      same loud skip.

WHAT COUNTS AS A BINDING
Not "the name appears somewhere". Each language has one anchored region — the
gRPC service impl, the host-client call surface — and only names found inside it
count. A registered TypeScript handler whose body answers `UNIMPLEMENTED` does
NOT count, because on the wire an `Unimplemented` reply is indistinguishable
from an absent hook, and that equivalence is the protocol's forward-compat
contract. If an anchor stops matching, this script fails loudly rather than
reporting an empty scan as a clean bill of health.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import spec  # noqa: E402

REPO_ROOT = spec.REPO_ROOT
ALL_RULES = ("R1", "R2", "R3", "R4", "R5", "R6")


class AnchorError(Exception):
    """A source-scan anchor stopped matching. Never silently downgraded."""


def snake(rpc: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", rpc).lower()


# ── source scanning ──────────────────────────────────────────────────────────

def _read(rel: str) -> tuple[str, list[str]]:
    path = REPO_ROOT / rel
    if not path.exists():
        raise AnchorError(f"{rel}: file is gone — update tools/parity/check.py")
    text = path.read_text(encoding="utf-8")
    return text, text.splitlines()


def _region(rel: str, start_re: str, end_re: str | None) -> list[str]:
    """Lines between the first `start_re` match and the next `end_re` match."""
    _, lines = _read(rel)
    start = next((i for i, l in enumerate(lines) if re.search(start_re, l)), None)
    if start is None:
        raise AnchorError(
            f"{rel}: the parity checker's anchor /{start_re}/ no longer matches. "
            f"The scan region moved; update tools/parity/check.py rather than trusting "
            f"an empty scan."
        )
    if end_re is None:
        return lines[start:]
    end = next((i for i in range(start + 1, len(lines)) if re.search(end_re, lines[i])), len(lines))
    return lines[start:end]


def scan_rust_capability() -> dict[str, str]:
    rel = "astra-plugin-sdk/src/runner.rs"
    region = _region(rel, r"^impl.*PluginCapabilityService\b", r"^#\[cfg\(test\)\]")
    found = {}
    for line in region:
        m = re.match(r"    async fn ([a-z_][a-z0-9_]*)\s*\(", line)
        if m:
            found[m.group(1)] = rel
    return found


def scan_rust_host() -> dict[str, str]:
    rel = "astra-plugin-sdk/src/host_client.rs"
    region = _region(rel, r"^//!|^use |^pub |^impl ", r"^#\[cfg\(test\)\]")
    found = {}
    for line in region:
        for m in re.finditer(r"\.([a-z_][a-z0-9_]*)\(\s*proto::", line):
            found[m.group(1)] = rel
    return found


def scan_python_capability() -> dict[str, str]:
    rel = "astra-plugin-sdk-python/astra_plugin_sdk/plugin.py"
    region = _region(rel, r"^class _CapabilityServicer\b", None)
    found = {}
    for line in region:
        m = re.match(r"    async def ([A-Z]\w*)\s*\(", line)
        if m:
            found[snake(m.group(1))] = rel
    return found


def scan_python_host() -> dict[str, str]:
    rel = "astra-plugin-sdk-python/astra_plugin_sdk/host_client.py"
    text, _ = _read(rel)
    found = {}
    for m in re.finditer(r"_stub\.([A-Z]\w*)\s*\(", text):
        found[snake(m.group(1))] = rel
    if not found:
        raise AnchorError(f"{rel}: no `_stub.<Rpc>(` call found — the host-client shape changed")
    return found


def scan_ts_capability() -> dict[str, str]:
    """Handler-map keys, minus the ones whose body answers UNIMPLEMENTED."""
    rel = "astra-plugin-sdk-ts/src/plugin.ts"
    region = _region(rel, r"private capabilityHandlers\(\)", r"as unknown as HandlerMap")
    entries: list[tuple[str, list[str]]] = []
    for line in region:
        m = re.match(r"      ([A-Z]\w*)\s*:", line)
        if m:
            entries.append((m.group(1), []))
        elif entries:
            entries[-1][1].append(line)
    if not entries:
        raise AnchorError(f"{rel}: the capability handler map is empty — the anchor moved")
    return {
        snake(name): rel
        for name, body in entries
        if "UNIMPLEMENTED" not in "\n".join(body)
    }


def scan_ts_host() -> dict[str, str]:
    rel = "astra-plugin-sdk-ts/src/host-client.ts"
    declared = _region(rel, r"^const REQUIRED_METHODS", r"\] as const;")
    names = set(re.findall(r'"([A-Z]\w*)"', "\n".join(declared)))
    text, _ = _read(rel)
    names |= set(re.findall(r"(?:this\.)?stub\.([A-Z]\w*)\s*\(", text))
    names |= set(re.findall(r'this\.unary(?:<[^>]*>)?\(\s*"([A-Z]\w*)"', text))
    if not names:
        raise AnchorError(f"{rel}: no host method names found — the anchor moved")
    return {snake(n): rel for n in names}


SCANNERS = {
    ("rust", "daemon->plugin"): scan_rust_capability,
    ("rust", "plugin->daemon"): scan_rust_host,
    ("python", "daemon->plugin"): scan_python_capability,
    ("python", "plugin->daemon"): scan_python_host,
    ("typescript", "daemon->plugin"): scan_ts_capability,
    ("typescript", "plugin->daemon"): scan_ts_host,
}


# ── proto scanning ───────────────────────────────────────────────────────────

def scan_proto(rel: str) -> dict[str, tuple[str, str]]:
    """{Rpc: (service, streaming)} for the two plugin-facing services."""
    text, _ = _read(rel)
    out: dict[str, tuple[str, str]] = {}
    for service in spec.SERVICES:
        m = re.search(r"^service\s+" + service + r"\s*\{", text, re.M)
        if not m:
            raise AnchorError(f"{rel}: `service {service}` not found")
        depth, i = 0, m.end() - 1
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = text[m.end():i]
        for rpc in re.finditer(
            r"\brpc\s+(\w+)\s*\(\s*(stream\s+)?[\w.]+\s*\)\s*returns\s*\(\s*(stream\s+)?[\w.]+\s*\)",
            body,
        ):
            name, req_stream, res_stream = rpc.group(1), bool(rpc.group(2)), bool(rpc.group(3))
            kind = {
                (False, False): "unary",
                (False, True): "server",
                (True, False): "client",
                (True, True): "bidi",
            }[(req_stream, res_stream)]
            out[name] = (service, kind)
    return out


# ── rules ────────────────────────────────────────────────────────────────────

def rule_R1(doc, bindings) -> list[str]:
    fails = []
    for hook in doc["hooks"]:
        for lang in spec.LANGUAGES:
            bound = snake(hook["rpc"]) in bindings[lang]
            if hook[lang] == "stable" and not bound:
                fails.append(
                    f"R1  {hook['rpc']}: spec says {lang}=stable, but no binding is in "
                    f"{spec.LANGUAGE_LABELS[lang]}'s source. Either implement it or "
                    f"downgrade the row to `planned`/`n/a`."
                )
            elif hook[lang] == "n/a" and bound:
                fails.append(
                    f"R1b {hook['rpc']}: spec says {lang}=n/a "
                    f"(\"{hook.get(f'{lang}_reason', '')}\"), but "
                    f"{bindings[lang][snake(hook['rpc'])]} binds it. Promote the row to `stable`."
                )
    return fails


def rule_R2(doc, bindings) -> list[str]:
    known = {snake(h["rpc"]) for h in doc["hooks"]}
    directions = {snake(h["rpc"]): h["direction"] for h in doc["hooks"]}
    fails = []
    for lang in spec.LANGUAGES:
        for name, where in sorted(bindings[lang].items()):
            if name not in known:
                fails.append(
                    f"R2  {name}: {where} binds an rpc with no row in spec/hooks.yaml. "
                    f"Add the row (with its daemon call site) or delete the binding."
                )
    for lang in spec.LANGUAGES:
        for name, where in sorted(bindings[lang].items()):
            if name in known and directions[name] != bindings["_direction"][lang][name]:
                fails.append(
                    f"R2  {name}: {where} binds it as {bindings['_direction'][lang][name]}, "
                    f"but the spec says {directions[name]}."
                )
    return fails


def rule_R3(doc, proto_rpcs) -> list[str]:
    rows = {h["rpc"]: h for h in doc["hooks"]}
    fails = []
    for rpc, (service, kind) in sorted(proto_rpcs.items()):
        row = rows.get(rpc)
        if row is None:
            fails.append(
                f"R3  {rpc}: declared on {service} in {doc['proto']} and has no row in "
                f"spec/hooks.yaml. Every plugin-facing rpc needs one — an undeclared hook "
                f"is how the SDKs drifted in the first place."
            )
            continue
        if row["service"] != service:
            fails.append(f"R3b {rpc}: spec says {row['service']}, the proto says {service}.")
        if row["streaming"] != kind:
            fails.append(
                f"R3c {rpc}: spec says streaming={row['streaming']}, the proto says {kind}."
            )
    for rpc in sorted(rows):
        if rpc not in proto_rpcs:
            fails.append(
                f"R3b {rpc}: spec/hooks.yaml has a row for an rpc {doc['proto']} does not "
                f"declare on either plugin-facing service."
            )
    return fails


def rule_R4(doc, today: datetime.date) -> list[str]:
    fails = []
    for hook in doc["hooks"]:
        for lang in spec.LANGUAGES:
            if hook[lang] != "planned":
                continue
            deadline = spec.grace_until(hook, lang)
            if deadline and deadline < today:
                overdue = (today - deadline).days
                fails.append(
                    f"R4  {hook['rpc']}: {lang} was planned until {deadline} — {overdue} day(s) "
                    f"overdue (tracked in {hook[f'{lang}_issue']}). Ship it, or move the date "
                    f"deliberately and say why."
                )
    return fails


def _daemon_root(doc, astra_dir: Path) -> Path | None:
    root = astra_dir / Path(doc["astra_daemon_root"]).name
    if root.exists():
        return root
    root = astra_dir / "astra-daemon"
    return root if root.exists() else None


def _provenance_probe(hook: dict) -> tuple[re.Pattern, str]:
    name = snake(hook["rpc"])
    if hook["direction"] == "daemon->plugin":
        return re.compile(r"\." + name + r"\s*\("), "call site"
    return re.compile(r"async fn " + name + r"\s*\("), "handler"


def rule_R5(doc, astra_dir: Path | None) -> tuple[list[str], str | None]:
    if astra_dir is None:
        return [], (
            "R5  SKIPPED: no Astra checkout. Set $ASTRA_RS_DIR or put one at ../Astra/astra-rs. "
            "The `daemon_calls` provenance in spec/hooks.yaml is UNVERIFIED in this run."
        )
    root = _daemon_root(doc, astra_dir)
    if root is None:
        return [], f"R5  SKIPPED: {astra_dir} has no astra-daemon/ — provenance UNVERIFIED."

    fails = []
    # A line that merely MOVED is not a finding. The daemon's plugin host is edited
    # every phase, so pinning exact line numbers made R5 fail on work that had
    # nothing to do with parity — twice, and both times the fix was mechanical.
    # What R5 is actually for is the branch below it: the call site is GONE, meaning
    # the daemon stopped calling a hook the spec still calls routed. That stays a
    # hard failure. Drift is reported as a note and repaired by --fix-provenance.
    drifted = []
    for hook in doc["hooks"]:
        if hook["daemon_calls"] == "none":
            continue
        rel, _, lineno = str(hook["daemon_calls"]).rpartition(":")
        path = root / rel
        if not path.exists():
            fails.append(f"R5  {hook['rpc']}: {hook['daemon_calls']} — no such file under {root}")
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        pattern, what = _provenance_probe(hook)
        idx = int(lineno) - 1
        if 0 <= idx < len(lines) and pattern.search(lines[idx]):
            continue
        elsewhere = [i + 1 for i, l in enumerate(lines) if pattern.search(l)]
        if elsewhere:
            drifted.append(f"{hook['rpc']} {rel}:{lineno}->{elsewhere[0]}")
        else:
            fails.append(
                f"R5  {hook['rpc']}: routing={hook['routing']} claims {hook['daemon_calls']}, "
                f"but no {what} for `{snake(hook['rpc'])}` exists anywhere in {rel}. Either the "
                f"daemon stopped calling this hook — in which case it is `unrouted`, and that is "
                f"a finding, not a line-number fix — or the provenance names the wrong file."
            )
    note = None
    if drifted:
        note = (
            f"R5  {len(drifted)} provenance line(s) drifted (the call site still exists, it just "
            f"moved): {', '.join(drifted[:6])}"
            + (f", +{len(drifted) - 6} more" if len(drifted) > 6 else "")
            + ". Not a failure. Run `check.py --fix-provenance` to re-point them."
        )
    return fails, note


def rule_R6(doc, astra_dir: Path | None) -> tuple[list[str], str | None]:
    """A host row's `permission` must be what `require_permission` actually reads.

    §5.6 gates the plugin->daemon direction on `[permissions]`, and the daemon
    holds that mapping in ONE table — `HOST_RPC_PERMISSIONS` in
    `astra-daemon/src/plugins/host_service.rs`, which its own test pins to
    `astra.proto`'s service block. This rule makes `spec/hooks.yaml` a third
    reader of that table rather than a second copy of it.

    It matters because the failure is silent in the worst direction. If the spec
    says a call needs nothing and the daemon gates it, the generated docs tell an
    author to ship a manifest that is denied on a user's machine. If the spec
    names a permission the daemon dropped, the consent sheet grows a checkbox
    that buys nothing — and boxes that protect nothing are how users learn to
    tick boxes.

    Parsed as text, not linked: this repo has no Rust toolchain requirement and
    CI runs it on a bare Python. Same optionality as R5 — no checkout, no check,
    said out loud.
    """
    if astra_dir is None:
        return [], (
            "R6  SKIPPED: no Astra checkout. Set $ASTRA_RS_DIR or put one at ../Astra/astra-rs. "
            "The `permission` column in spec/hooks.yaml is UNVERIFIED in this run."
        )
    root = _daemon_root(doc, astra_dir)
    if root is None:
        return [], f"R6  SKIPPED: {astra_dir} has no astra-daemon/ — permissions UNVERIFIED."

    path = root / "src/plugins/host_service.rs"
    if not path.exists():
        return [], f"R6  SKIPPED: {path} does not exist — permissions UNVERIFIED."
    text = path.read_text(encoding="utf-8", errors="replace")
    _, _, after = text.partition("HOST_RPC_PERMISSIONS")
    body, _, _ = after.partition("];")
    if not body:
        return [f"R6  {path}: HOST_RPC_PERMISSIONS not found — the anchor moved."], None

    # ("FireTrigger", Some(Permission::FireTrigger)) | ("Register", None)
    daemon: dict[str, str] = {}
    for rpc, arg in re.findall(r'\(\s*"(\w+)"\s*,\s*((?:Some\s*\(\s*)?[\w:]+)', body):
        variant = arg.rpartition("::")[2] if "::" in arg else None
        daemon[rpc] = snake(variant) if variant else "none"
    if not daemon:
        return [f"R6  {path}: HOST_RPC_PERMISSIONS parsed as empty — the shape changed."], None

    fails = []
    for hook in doc["hooks"]:
        if hook["service"] != "PluginHostService":
            continue
        rpc, declared = hook["rpc"], hook["permission"]
        actual = daemon.get(rpc)
        if actual is None:
            fails.append(
                f"R6  {rpc}: spec/hooks.yaml gates it on `{declared}`, but the daemon's "
                f"HOST_RPC_PERMISSIONS has no row for it at all. A host rpc with no row "
                f"is ungated — that is a security finding, not a spec typo."
            )
        elif actual != declared:
            fails.append(
                f"R6  {rpc}: spec/hooks.yaml says `permission: {declared}`, the daemon "
                f"requires `{actual}`. The daemon is authoritative — fix the row, and if "
                f"the daemon is the one that changed, the generated docs and the registry "
                f"bot's RPC_RULES have to move with it."
            )
    missing = sorted(set(daemon) - {h["rpc"] for h in doc["hooks"]})
    if missing:
        fails.append(
            f"R6  the daemon gates {', '.join(missing)}, which spec/hooks.yaml has no row "
            f"for. R3 covers rpcs in the proto; this covers rpcs the daemon really guards."
        )
    return fails, None


def fix_provenance(doc, astra_dir: Path | None) -> int:
    """Re-point `daemon_calls` at lines that merely moved.

    Deliberately narrow. It moves a line number when the same call site is
    findable elsewhere in the same file, and does NOTHING when a hook's call
    site has vanished — that is the daemon dropping a hook, and no tool should
    paper over it.
    """
    if astra_dir is None:
        print("--fix-provenance needs an Astra checkout; none found.", file=sys.stderr)
        return 2
    root = _daemon_root(doc, astra_dir)
    if root is None:
        print(f"--fix-provenance: {astra_dir} has no astra-daemon/.", file=sys.stderr)
        return 2

    text = spec.SPEC_PATH.read_text(encoding="utf-8")
    moved = 0
    for hook in doc["hooks"]:
        if hook["daemon_calls"] == "none":
            continue
        rel, _, lineno = str(hook["daemon_calls"]).rpartition(":")
        path = root / rel
        if not path.exists():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        pattern, _what = _provenance_probe(hook)
        idx = int(lineno) - 1
        if 0 <= idx < len(lines) and pattern.search(lines[idx]):
            continue
        hits = [i + 1 for i, l in enumerate(lines) if pattern.search(l)]
        if not hits:
            continue
        old = f'    daemon_calls: "{hook["daemon_calls"]}"'
        new = f'    daemon_calls: "{rel}:{hits[0]}"'
        if text.count(old) != 1:
            print(f"--fix-provenance: {hook['rpc']}: `{old.strip()}` is not unique; fix by hand.",
                  file=sys.stderr)
            continue
        text = text.replace(old, new)
        print(f"moved  {hook['rpc']}: {hook['daemon_calls']} -> {rel}:{hits[0]}")
        moved += 1
    if moved:
        spec.SPEC_PATH.write_text(text, encoding="utf-8")
        print(f"{moved} provenance line(s) re-pointed. Re-run `python3 tools/parity/gen.py`.")
    else:
        print("provenance: nothing to move.")
    return 0


# ── driver ───────────────────────────────────────────────────────────────────

def resolve_astra_dir(explicit: str | None) -> Path | None:
    """An explicit --astra-dir that does not exist is an error, not a quiet skip."""
    if explicit is not None:
        if not Path(explicit).is_dir():
            raise AnchorError(f"--astra-dir {explicit} is not a directory")
        return Path(explicit)
    for candidate in (os.environ.get("ASTRA_RS_DIR"), REPO_ROOT.parent / "Astra" / "astra-rs"):
        if candidate and Path(candidate).is_dir():
            return Path(candidate)
    return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rules", default=",".join(ALL_RULES), help="comma-separated subset, e.g. R1,R4")
    parser.add_argument("--astra-dir", default=None, help="path to Astra/astra-rs for R5 and R6")
    parser.add_argument("--today", default=None, help="ISO date, for testing R4")
    parser.add_argument(
        "--fix-provenance",
        action="store_true",
        help="re-point daemon_calls at call sites that merely moved, then exit",
    )
    args = parser.parse_args(argv)

    selected = [r.strip() for r in args.rules.split(",") if r.strip()]
    unknown = [r for r in selected if r not in ALL_RULES]
    if unknown:
        print(f"unknown rule(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    try:
        doc = spec.load()
    except spec.SpecError as exc:
        print(f"spec/hooks.yaml is malformed:\n  {exc}", file=sys.stderr)
        return 2

    try:
        bindings: dict = {"_direction": {}}
        for lang in spec.LANGUAGES:
            merged: dict[str, str] = {}
            per_direction: dict[str, str] = {}
            for direction in ("daemon->plugin", "plugin->daemon"):
                for name, where in SCANNERS[(lang, direction)]().items():
                    merged[name] = where
                    per_direction[name] = direction
            bindings[lang] = merged
            bindings["_direction"][lang] = per_direction
        proto_rpcs = scan_proto(str(doc["proto"]))
    except AnchorError as exc:
        print(f"parity scan could not run:\n  {exc}", file=sys.stderr)
        return 2

    today = datetime.date.fromisoformat(args.today) if args.today else datetime.date.today()
    try:
        astra_dir = resolve_astra_dir(args.astra_dir)
    except AnchorError as exc:
        print(f"parity scan could not run:\n  {exc}", file=sys.stderr)
        return 2

    if args.fix_provenance:
        return fix_provenance(doc, astra_dir)

    failures: list[str] = []
    skips: list[str] = []
    if "R1" in selected:
        failures += rule_R1(doc, bindings)
    if "R2" in selected:
        failures += rule_R2(doc, bindings)
    if "R3" in selected:
        failures += rule_R3(doc, proto_rpcs)
    if "R4" in selected:
        failures += rule_R4(doc, today)
    if "R5" in selected:
        r5, skip = rule_R5(doc, astra_dir)
        failures += r5
        if skip:
            skips.append(skip)

    if "R6" in selected:
        r6, skip = rule_R6(doc, astra_dir)
        failures += r6
        if skip:
            skips.append(skip)

    counts = ", ".join(
        f"{lang}={len(bindings[lang])}" for lang in spec.LANGUAGES
    )
    print(
        f"parity: {len(doc['hooks'])} spec rows, {len(proto_rpcs)} plugin-facing rpcs in "
        f"{doc['proto']}, bindings scanned: {counts}"
    )
    for skip in skips:
        print(skip)

    if failures:
        print(f"\n{len(failures)} parity failure(s):\n", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nspec/hooks.yaml is the source of truth. Fix the code, or fix the row and "
            "re-run `python3 tools/parity/gen.py`.",
            file=sys.stderr,
        )
        return 1

    print(f"parity: rules {', '.join(selected)} pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
